# MedSta 设计思路与关键决策记录

> 记录跨模块的架构决策与理由。单功能的设计细节写在对应 spec 内；本文只放"需要读多个文件才能理解"的决策。

## 1. Agently Owner 划分（依据 agently skill 的所有权规则）

原则：**模型只拥有语义决策；schema 校验、枚举约束、算术与副作用全部归宿主代码。**

| 职责 | Owner | 说明 |
|---|---|---|
| 一次模型交互与输出契约 | `ModelRequest` | 方案生成 / 结果解释 / ReAct 推理，用 `.input/.info/.instruct/.output` 四段式声明结构化输出；每个消费字段的类型、语义、可空性、取值范围显式声明 |
| 一次 ReAct 讨论回合 | `AgentExecution` | 讨论态智能体运行，选择 producer、controls 与流 |
| Pipeline 应用层编排 | `TriggerFlow` | "确认→执行→交付→修正回讨论"是开发者拥有的编排：分支（修正分支）、顺序步骤、运行状态与恢复 |
| 会话/任务信息 | `TaskContext` | 消费者绑定的信息读取，不手工拼接全局上下文 |
| 数据文件与 artifact | `TaskWorkspace` | 上传数据集、生成的图表文件统一归 workspace |
| 会话与执行记录 | `RecordStore` | 可恢复的持久记录，支撑回溯与再对齐 |

反模式禁止：自定义状态存储、重试管理器、关键词/正则做语义判断、未经消费的输出字段、把原始数据全量塞进 prompt。

## 2. 模型输出契约：AnalysisPlan

讨论态最终产出结构化 `AnalysisPlan`（步骤数组：步骤名、统计方法、目标列、图表类型、参数），由宿主代码做 schema 校验后进入执行态。模型不产出可执行代码——pipeline 步骤是宿主实现的确定性操作（统计/预测/绘图），模型只决定"用哪一步、什么参数"。这保证执行可测试、可复现、可解释。

## 3. TDD 约定（依据 tdd skill）

- 垂直切片：一个行为 → 一个测试（RED）→ 最小实现（GREEN）→ 下一行为。禁止先写全部测试再写全部实现。
- 测试走公共接口（API/服务层函数），不测私有方法；仅在模型调用与文件系统边界使用模拟/临时目录。
- 模型相关测试：默认模拟模型验证结构化契约与确定性分支；真实模型调用仅做最小的、显式标记的验证（可跳过）。
- spec 的行为列表即测试循环队列，spec 敲定（进入 implementing）才开始写测试。

## 4. 会话状态机

会话状态：`discussing（讨论态）→ plan_confirmed（方案确认）→ executing（执行中）→ delivered（已交付）→（修正意见）→ discussing`。
状态由宿主 `SessionManager` 管理（确定性状态机，非模型决策）；模型只参与 discussing 态的内容生成。

**转移表强约束（2026-10-24 审查修复）**：`manager.transition` 此前是无条件赋值——状态机只存在于注释里，
存在两条实际可触发的非法路径：DELIVERED 态 `confirm_plan` 会用残留的 `session.plan` 直接重跑旧方案；
PLAN_CONFIRMED 期重复 confirm 会重复下发 `chart_config`。现以 `_ALLOWED_TRANSITIONS`
（源状态 → 允许目标集合）在 `manager.py` 宿主侧强约束：DISCUSSING→{DISCUSSING, PLAN_CONFIRMED, EXECUTING}、
PLAN_CONFIRMED→{EXECUTING, DISCUSSING}、EXECUTING→{DELIVERED, DISCUSSING}、
DELIVERED→{DISCUSSING, DELIVERED}。非法转移抛 `InvalidStateTransition(ValueError)`，
由 `service.handle` 统一转换为 `PROTOCOL_UNSUPPORTED` 错误帧（协议顺序错误语义，manager 不依赖 errors 模块保持分层）。

## 5. 流式与持久化策略

- WebSocket 推送讨论消息、pipeline 步骤进度、artifact 就绪事件。
- 数据解析在任务内一次性完成并缓存画像，后续讨论只携带画像摘要而非全量数据（避免上下文膨胀）。
- 绘图后台生成文件，就绪后推送事件引用 artifact 路径，不在消息体里内联大图。

## 6. 生命周期与时间线

- spec 生命周期：`draft → designing → implementing → done`，放弃则 `archived`；规则见 `spec/README.md`。
- 每次流转在 `docs/timeline.md` 追加一行（日期、spec、动作、说明），保证治理可审计。

## 7. 测试架构（spec 019）

四层金字塔，越往下越依赖真实实现，仅在系统边界（模型网络调用、文件系统）注入假实现：

| 层 | 入口 | 隔离手段 | 关注点 |
|---|---|---|---|
| 方法层 | `stats.registry.execute_step`、`data.profiler`、`plotting.render_chart` | `tmp_path` 作为 artifact 目录 | 数值口径、策略链、PNG 产物契约 |
| 编排层 | `SessionService.handle`、`AnalysisWorkflow` | 注入 `RecordingFakeRequest` / 假 gateway | 状态机、事件序列、记录分桶 |
| 契约层 | `TestClient` REST + `websocket_connect` | `app.state.data_root` 指向 `tmp_path`，`SessionManager.clear()` 清场 | 请求/响应/事件契约、错误码 |
| 前端层 | Vitest + Testing Library / Playwright | 只 mock `fetch` 与 `WebSocket`；浏览器层用桩模型后端 | 布局、交互、前后端契约 |

关键决策：

- **数据根请求期解析**：`routes_data.DATA_ROOT` 原本是导入期常量，测试会污染真实 `backend/data/sessions`。
  改为请求期读取 `request.app.state.data_root`（回退环境变量），`create_app()` 注入同一路径；
  生产行为零变更，测试只需覆盖 app state。
- **全局单例清场**：`SessionManager` 是模块级单例，`clear()` 是显式测试接缝，避免测试间串味；
  不为测试引入依赖注入框架。
- **桩模型后端**：`backend/tests/e2e_app.py` 以 `create_app()` 为基础替换 `app.state.service` 的 agent，
  供 Playwright `webServer` 启动；不触碰生产装配路径。
- **真模型隔离**：`tests/test_real_llm_smoke.py` 用 `MEDSTA_REAL_LLM=1` 且存在 `LLM_API_KEY` 才运行，
  并在 `pyproject.toml` 注册 `real_llm` marker，默认 CI 不消耗额度。
- **前端代理可参数化**：`vite.config.ts` 的 proxy target 读 `MEDSTA_API`，E2E 用 5174→8021，
  与本地 dev（5173→8000）互不干扰。

## 8. 正确性护栏（spec 020）

- **列名词元匹配而非子串**：`age` 是 `stage`/`percentage` 的子串，英文列名按 `[^a-z0-9]+` 切词后与白名单求交集；
  中文（年龄/血压…）无词边界，使用子串匹配。列名只作为辅助信号，用户仍可在类型确认卡修正。
- **整数测量变量判连续**：列名命中白名单优先；否则非负且 `max-min ≤ 10` 判 `ordinal`（Likert/评分/分级），
  宽范围整数计数判 `continuous`；0/1 保持 `ordinal` 以免波及类型映射契约。
- **Logistic 分离三重检测**：未收敛、`max|β| ≥ 15`（OR≈3.3e6）、OR/CI 非有限，任一命中即拒绝并给出可操作建议。
  阈值取安全方向：宁可拒绝输出，也不下发不可估计的 OR；Firth 惩罚留作后续能力。
- **协议错误码独立**：未知 WS 消息用 `PROTOCOL_UNSUPPORTED`，`INVALID_PLAN` 只表示方案校验失败，
  避免前端把「版本不匹配」误读为「方案要改」。

## 9. CI 流水线（spec 021）

- **三作业并行**：backend（pytest + 覆盖率门槛）、frontend（lint/build/vitest）、e2e（Playwright）。
  拆分依据是失败定位与运行环境：E2E 需要 Python + Node 双环境，独立成 job 不污染前后端。
- **覆盖率门槛按实测定**：2026-10-21 语句覆盖率 88.19%，门槛取 83%（向下取整再 −5pt），
  目的是防大幅倒退而非追求数字；前端沿用 v8 报告，暂不设硬阈值。
- **E2E 安装 CJK 字体**：Ubuntu runner 默认无中文字体，安装 `fonts-noto-cjk` 以覆盖真实中文图表路径；
  不安装时英文回退也能通过，但会失去该路径验证。
- **本地镜像脚本**：`scripts/ci.sh` 复用同一组命令，解决「没有远端就无法验证流水线」的问题；
  通过 `COVERAGE_MIN=99` 实测过失败会立即中断并透传非零退出码。
- **推送与保护分离**：代码推送到 `main` 后 Actions 自动运行；分支保护（CI 必过）属于仓库设置，
  脚本无法代劳，需在 GitHub 后台手动开启。

## 10. 结果解释与交付后答疑（spec 022）

- **因果守卫是合规安全守卫，不是语义路由**：它拦的是「治疗组导致结局改善」这类会被用户当作临床结论的断言，
  属于与 schema 校验同类的确定性红线，而非「用正则判断模型在想什么」。实现按「因素/干预/治疗/用药/分组/暴露/变量/指标
  + 0–12 字 + 导致/引起/造成/使得/决定/证明/致使」匹配，并对匹配串及前 12 字内的否定词
  （不能/无法/不足以/并不/未/不应/不可/不代表/不等于）豁免，保留「不能说明存在因果关系」这类正确表述。
- **证据白名单而非整份 result**：`StepResult.result` 是各方法自行拼装的 dict，键不统一且可能含整张表。
  宿主按 method 取固定键（见 `agents/interpretation.py::_SIMPLE_KEYS`），prompt 体积恒定在 1–2k tokens，
  同时消除「模型自己算数」的机会。失败步骤也要给 `error.code/message`，否则无法解释「为什么没做成」。
- **数值软标、因果硬门**：模型对 p 值做四舍五入（0.0287→0.03）是合法改写，误报会让角标失效；
  因此数值走「允许集 + 四舍五入 + `p<0.001` 形式放行」后只标记不拒绝。因果断言零容忍：重试一次仍违规则整段不展示。
- **解释是非阻塞增强项**：`review_request` 先发，解释后台生成后再推 `interpretation`；任何异常都静默丢弃，
  绝不把 error 事件推给用户。用报告步骤签名 `[(method, title), ...]` 比对防串台（新执行覆盖旧报告时丢弃）。
- **交付态路由归状态机**：不在 service 里新增 `revise_mode` 之类状态；`_on_chat` 读 `SessionStatus.DELIVERED`
  决定答疑，`review {"decision":"revise"}` 读同一状态回讨论。前端只呈现，不决定服务端路由。
- **句数控制由宿主截断**：提示词声明上限只是提高服从率，真正生效的是按 `[。！？]` 切分后取前 N 句；
  不用英文句点，避免切坏小数。`MEDSTA_INTERPRET=0` 可整体关闭，`MEDSTA_INTERPRET_MAX_SENTENCES` 默认 1、clamp 到 1–5。

## 11. 教材口径校准（spec 023）

- **分布判定是单一入口**：`stats/descriptive.py::classify_distribution` 同时服务「描述指标推荐」与「参考值范围方法选择」，
  避免两处规则漂移。四态而非两态：`insufficient` 单独列出，因为 n<3 或取值过少时任何正态性检验都不可靠，
  给结论比给「非正态」更危险。
- **离散数据的正态性检验不适用**：滴度、评分这类取值很少的列，Shapiro 会因连续假设被违反而拒绝。
  判定时若对数变换后不同取值 ≤6 个，跳过 Shapiro 改用偏度；这是教材「对数变换后呈对称分布」的数值化近似。
- **描述与描述性统计分离**：`describe` 保持七列不变（画像、导出、既有断言零波及），
  完整口径进 `descriptive_stats`。两者分工写进工具目录 description，避免模型选错。
- **区间必须与方法同源**：均值差区间用 t 临界值，自由度随方法变化（合并方差 df=n1+n2−2、Welch–Satterthwaite、配对 n−1）；
  非参数方法不套用均值差区间，改报中位数差 + bootstrap。键名 `ci_target` 标明区间究竟是均值差还是中位数差。
- **配对的前提检验对象是差值**：对原始两组做 Shapiro 会把「配对设计」当「独立两组」处理，
  进而错选 Mann-Whitney U。配对非正态应走 Wilcoxon 符号秩。
- **`method_note` 由宿主写入，不是模型生成**：文案集中在 `stats/notes.py`，`execute_step` 兜底挂载，
  新增方法只要登记文案就自动生效；前端默认折叠，避免挤占结论区。
- **教材例题作为外部基准**：`tests/test_textbook_conformance.py` 内联例 2-2/2-6/3-3/11-2 的原始数据与结果，
  任何口径改动都会与教材数值对撞。例 11-2 的 r=0.801 恰在 0.8 分档边界（正文称「较高」、规则为「很高」），
  测试只锁定 r 数值，分档用非边界数据验证。

## 12. 第六至十章口径与教材/软件取舍（spec 024）

- **教材优先、软件默认保留**：两独立样本方差齐性按教材用 F 检验（α=0.10）而非 Levene α=0.05；
  ANOVA 事后默认 SNK-q 而非 Holm；四格表按 n 与最小期望频数三档判定而非「期望<5 比例」。
  三处都在 `statistics-methods.md` 的对照表里写明，不静默替换，因为读者需要知道结论是按哪套口径得出的。
- **教材未给公式时如实标注**：多组秩和事后在教材里只有一句「参考相关书籍」，实现采用 Dunn + Bonferroni，
  并在 `method_note` 与多重性提醒里写明「教材未给公式，采用通用做法」，不冒充教材口径。
- **SNK 逐步规则的可见性**：教材规定跨度最大的比较不显著时后续不再判定。实现保留全部原始 p 值，
  另给 `significant` 与 `step_down` 标记，避免用户看到「p<0.05 却被判不显著」而无从解释。
- **大样本正态判定不能只依赖 Shapiro**：1009 例基线数据实测中，年龄偏度仅 −0.16，但 Shapiro P=4.6e-07
  （n 越大越敏感），导致推荐中位数。修正为：n≥500 时以偏度为主判据；同时新增「单一取值占比>50%」
  判定，用于 VAS 这类两端堆积的评分（0 与 8 占多数），避免把离散堆积误判为正态。
- **率的分子必须显式**：`chi_square` 的 `group_rates` 默认取列联表第一列，但列顺序由字符串排序决定
  （「无效」可能排在「有效」前），因此新增 `event_value` 参数，并在输出 `rate_column` 标注，
  避免「有效率」被算成「无效率」而不自知。
- **布尔参数的向后兼容**：`chi_square.correction` 由 boolean 改为 choice（auto/yes/no），
  `validate_step` 与 `normalize_params` 统一把 True/False 映射为 yes/no，旧计划不会因枚举变化被拒。

## 13. 教材未给公式时的外部标准引入规则（spec 025）

- **先确认「教材到底给了什么」再动手**：逐关键词检索后确认，Tukey/Dunnett/LSD/Scheffé 只在表 8-9
  出现一次，析因与重复测量只在练习题选项与设计章节提及，检验效能只有 1−β 概念。
  因此这些实现不能声称「按教材」，必须在 `method_note` 与 `statistics-methods.md` 标注外部依据。
- **优先复用成熟实现，不手写统计分布**：Dunnett 直接用 `scipy.stats.dunnett`（多元 t 的单步检验），
  析因用 `statsmodels.anova_lm(typ=2)`，重复测量用 `AnovaRM`，样本量用 `statsmodels.stats.power`。
  只有 Tukey/LSD/Scheffé 这三个由 `studentized_range` 与 F/t 分布组合即可表达的，才写纯函数。
- **Dunnett 的随机源必须固定**：`scipy.stats.dunnett` 内部含数值积分/模拟，同一份数据两次调用 p 值会差几个百分点
  （实测 1.96e-4 vs 2.52e-4）。实现固定 `random_state=default_rng(20261023)`，测试用同一种子，
  否则「结果可复现」这条硬门无法成立。
- **事后比较不拆成独立工具**：四种方法共用同一次 ANOVA 的 `MS误差` 与 `df误差`，
  拆分会导致重复计算、以及「用错误差项」的静默错误。因此并入 `anova.correction`，
  并在 Kruskal 路径显式忽略参数方法、退回 Dunn。
- **设计期工具允许没有目标列**：`sample_size` 的输入是研究设计参数而非数据，
  `validate_step` 用 `_NO_TARGET_TOOLS` 豁免「至少一个目标列」，`min_rows=0`、`charts=()`，
  避免为了满足校验而被迫填一个无关列。
- **能力不足要说出来**：重复测量未做球形性校正（Mauchly/Greenhouse-Geisser 均未实现），
  在 `sphericity_corrected=false`、`strategy.steps` 与 `method_note` 三处同时标注，而不是沉默。

## 14. 生存分析的边界（spec 027）

- **教材依据的存在性要先查实**：024/025 两轮我判断「教材无生存分析」，实际教材有第十四章（p.145）。
  教训是核对范围不能只看目录前段——`grep` 关键词（生存分析/Cox/删失）比读目录可靠。
  这也让 027 从「外部标准驱动」变为「教材口径驱动」，只有 RMST 与 PH 假设检验仍需外部依据。
- **删失不是缺失值**：删失个体在删失前仍贡献风险集信息，不能删除也不能当事件处理。
  这句话必须在 `method_note` 与策略链里说清楚，否则用户会把删失行当异常值删掉。
- **同时间点的排序影响结果**：教材规定完全数据排在删失数据之前（§14-2），
  实现用 `np.lexsort((event_priority, time))` 固化该规则；顺序反了会让风险集少一人，生存率系统性偏高。
- **多组 log-rank 不能只算第一组**：`χ²` 要用 `g−1` 维 `O−E` 向量与协方差矩阵求二次型；
  只对第一组求和会因各组方差被忽略而系统性偏大，这个问题在实现时容易看不见。
- **`PHReg` 的 `llr` 是 `None`**：statsmodels 不提供现成的似然比统计量，必须自建零模型
  `2*(llf_full−llf_null)`；直接取属性会得到 None 并静默错报。
  同理 `schoenfeld_residuals` 是**属性**而非方法，调用会抛 `TypeError`。
- **PH 假设不检验就等于默认成立**：Cox 的 HR 解释依赖比例风险假定，
  违反时 HR 是时间平均的混合效应。实现对每个协变量做 Schoenfeld 残差与时间的 Spearman 相关，
  `p<0.05` 时在策略链提示分层 Cox 或时依协变量，并标注该方法不在教材正文内。
- **RMST 的 τ 决定可比性**：默认取各组最大随访时间的最小值，保证两组在同一时间窗内；
  τ 超出某组随访时置 `truncated=True`，避免把「外推」当「观测」。

## 15. 缺失数据路径（spec 028）

- **教材 0 覆盖，必须标注外部依据**：缺失数据在教材中无任何章节，全部依据 Little & Rubin (2019) 与
  van Buuren (2018)。`method_note` 与 `statistics-methods.md` 都写明「教材未覆盖」，不冒充教材口径。
- **单数据集插补不是多重插补**：MICE 跑 m 次后取均值写出一份数据集，只能降低插补随机性，
  不能恢复「插补不确定性」对标准误的贡献。实现输出 `between_imputation_variance` 作为相对指示，
  并在字段、`method_note`、数据集名称三处声明；`capabilities.planned` 保留「完整 MI（Rubin 合并）未实现」。
- **每次插补用不同随机种子**：`random_state + index`。若 m 次都用同一种子，结果完全相同，
  `between_imputation_variance` 恒为 0，会给出「插补很确定」的错误信号。
- **不自动切换 active 数据集**：`data_profile` 事件会 `setActiveWorkspaceId`，复用它会打断用户当前视图。
  因此新增 `dataset_added` 事件，只追加标签页；用户手动切换才算真正换数据。
- **`_artifact_dir` 是内部保留键**：`execute_step` 注入而非工具目录参数，模型不可填写；
  未注入时 handler 不落盘但返回内存结果并提示，保证单元测试可直接调用 handler。
- **缺失机制只给提示**：不做 Little's MCAR 检验。用缺失模式形态 + 分组缺失差异卡方给 `mechanism_hint`，
  固定声明「不能仅凭数据断定 MCAR/MAR/MNAR」。把「提示」包装成「判定」会让用户误以为机制已被识别。
- **LOCF 只进敏感性**：前向填充会系统性压缩方差、扭曲时间趋势，作为主分析结果会高估精度；
  `sensitivity_only=true` 的方法一律不产出数据集。

## 16. 估计目标与 SAP 边界（spec 029）

- **教材 0 覆盖**：Estimand/SAP 在教材中无任何内容，全部依据 ICH E9(R1)。文案标注来源，不冒充教材。
- **状态是计算值，不是存储字段**：`sap_status` 由 `sap_status_of(plan)` 从五要素推导，
  不作为 `AnalysisPlan` 字段。这样模型不能写入「我是确证性分析」，前端也不能自行推导出另一种状态。
- **五要素齐全 ≠ 确证性**：系统无法验证事前注册、盲态与 SAP 冻结，措辞只能是
  「已声明估计目标」。这不是保守，而是防止把聊天里的几句话包装成研究方案。
  该约束用测试锁住：扫描前后端源码，出现 `pre-specified` 或用「确证性」正面描述本系统流程即失败。
- **`intercurrent_events` 不参与完整性判定**：允许空列表表示「无伴发事件」。
  若把空列表判为未声明，大量真实场景会被误标为探索性，反而让状态失去信息量。
- **字段全给默认空值**：模型常只填一部分。若 pydantic 因缺字段拒绝整份方案，
  用户会拿不到任何东西；正确做法是接受部分填写，由宿主判定与提示缺失项。
- **模型允许留空**：提示词明确「无法确定时留空，禁止编造人群与干预」。
  宁可停在探索性，也不要让模型编出「成年患者」「手术组 vs 保守组」这类看似专业实则无据的内容。
- **caveat 二选一而非叠加**：两条固定文案并列会互相稀释，用户读不出区别；
  `_sanitize` 先剔除两条固定文案再按状态追加一条。
- **不新增 WS 事件**：改五要素走现有 supplement/revise 让模型重出整份方案。
  这避免了 `estimand_update` 的部分更新语义与并发冲突，代价是重出方案——与该卡片现有交互一致。

## 17. 能力披露的维护规则（spec 030）

- **`planned` 不是备忘清单，是对外承诺的缺口**：它直接进 `/capabilities` 并被前端展示，
  用户会据此判断「这个工具能不能做某事」。写错等于误导。
- **必须写「已实现 X；未实现 Y」**：只列方法名（如「Holm / Hochberg / Dunnett」）时，
  读者无法区分哪些已做、哪些没做。`multiplicity_control` 曾因此长期暗示 Holm/Dunnett 未实现，
  实际它们在 025 已落地。
- **测试只能守结构，守不住语义**：直接判断「描述里的方法有没有实现」需要中文能力名到工具名的映射，
  硬做会大量误伤。因此测试守两条可判定的约束——每条 `planned` 的 `description` 必须含「未实现」
  或「不支持」；`planned` 的 `name` 不得与注册表键重名。前者逼作者表态，后者防「已实现仍挂 planned」。
- **落地一个能力时，必须回头改 planned**：这是唯一需要人记住的环节；测试只能在下一次跑时提醒
  「描述里没有未实现范围」，不能提醒「你该把它删了」。

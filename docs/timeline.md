# MedSta 开发时间线

> **用途**：记录「什么时候、因为什么、改变了什么结构或策略」。按日期**倒序**排列，最新在最上。
>
> **与其它文档的分工**
>
> | 文档 | 回答的问题 |
> |---|---|
> | `docs/timeline.md` | 什么时候、因为什么、改变了什么（决策与结构） |
> | `spec/done/*.md` | 某个功能做什么、行为列表、验收标准 |
> | `TO_DO.md` | 接下来做什么、优先级、已知限制 |
> | `docs/design-notes.md` | 某个技术决策的完整推理过程 |
>
> 本文件只记录**已发生**的事，不写计划、不写待办。

## 维护规则

**必须留一条的情形：**

1. 目录重组、模块拆分或合并、文件搬迁（含 spec 目录流转）。
2. 依赖版本、运行时、工具链变化（`pyproject.toml`、`package.json`、CI、环境）。
3. 流程、口径、校验规则、禁止项、验收门槛变化。
4. 技术选型定稿（在多个可行方案中做出结论）。
5. 产品范围增删、优先级调整、功能落地。
6. spec 阶段的重大回退或重写（未发布即推翻已定设计）。

**不必留条目的情形：** 纯 bug 修复且不改变契约、文案调整、内部重构且接口与行为不变（后者可在 commit message 里说明）。

**写法要求：**

- 一行一件事。内容列必须可核对：含文件路径、模块名、阈值、版本号、测试数。
- 原因列优先引用：教材章节号、评估报告门禁（G0–G7）、真实数据实测值、被修复的具体缺陷。
- 禁止「优化了性能」「完善了体验」这类无法验证的表述。
- 同一事件若既有功能落地又有决策，拆成两行（类型不同），不合并成长句。

**排序：** 日期倒序（`YYYY-MM-DD`，可字符串比较）；**同日**按 `需求 → 结构 → 规范 → 选型 → 环境 → 迁移` 排列。

## 类型定义

| 类型 | 判定标准 | 示例 |
|---|---|---|
| `迁移` | 仓库初始化、目录搬迁、文件迁移 | `git init` 并推送 main |
| `环境` | 运行时、依赖版本、工具链、外部服务 | scipy 下限提到 1.14 |
| `规范` | 流程、口径、校验规则、禁止项、验收门槛 | 两独立方差齐性改 F 检验 α=0.10 |
| `结构` | 模块拆分/合并、契约形态、分层、接口 | 新增 `stats/inference.py` |
| `选型` | 在多个可行方案中做出技术结论 | Dunnett 用 scipy 内置而非自实现 |
| `需求` | 产品范围增删、优先级调整、功能落地 | 022 结果解释完成 |

## 时间线

### 2026-10-23

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|

| 2026-10-23 | 需求 | 030 阶段评估与 P0 修复完成：`evaluation-report.md` 重写为 029 基线（含 019→029 六维度对比），修正 `competing_risk`/`multiplicity_control` 滞后描述，022–029 成果一次性入库 | 评估发现「八个 spec 无任何提交」与「planned 描述滞后」两项 P0 风险；报告综合分 7.4 → 7.9 |
| 2026-10-23 | 需求 | 029 Estimand/SAP 完成：`AnalysisPlan` 增估计目标五要素（人口/变量/处理/伴发事件+策略/汇总指标），`plan` 事件下发 `estimand` 与 `sap_status`，方案卡折叠展示并标「已声明估计目标」或「探索性分析」 | 教材对 Estimand/SAP 0 覆盖，依据 ICH E9(R1)；方案只说「用什么方法」不说「回答什么问题」 |
| 2026-10-23 | 需求 | 028 缺失数据路径完成：`missing_report` 升级为缺失模式诊断（univariate/monotonic/arbitrary + 分组差异提示 + 阈值警告），新增 `impute`（MICE 20 次取均值 + 插补间方差、median/mean/LOCF 仅敏感性、delta 扫描）并产出可继续分析的插补数据集 | 教材对缺失数据 0 覆盖，依据 Little & Rubin (2019)/van Buuren (2018)；此前只能报缺失率，无法处理 |
| 2026-10-23 | 需求 | 027 生存分析族完成：KM（含排序规则与 Greenwood SE）、中位生存期、风险人数表、log-rank/Breslow、Cox（HR/CI/LR/Wald/Score）、Schoenfeld PH 检查、RMST，新增 `survival_curve` 图表 | 教材第十四章存在但 024/025 两轮误判为「无」，本轮 `grep` 关键词核实后按教材口径实现；删失资料无法用横断面方法处理 |
| 2026-10-23 | 需求 | 025 事后比较与设计类方法完成：Tukey/Dunnett/LSD-t/Schéffé 并入 `anova.correction`；新增 `factorial_anova`、`repeated_measures_anova`、`sample_size` | 教材仅在表 8-9 列名称、在练习题与设计章节提设计类型、检验效能只有 1−β 概念，均无公式；用户要求补全 |
| 2026-10-23 | 需求 | 024 第六至十章口径完成：新增单样本检验、随机区组方差分析、配对 McNemar；ANOVA 事后改 SNK-q、四格表三档、多样本率 χ² 分割、Kendall τ | 复核教材目录发现第六至十章正文存在，此前只读了第二/三/十一章 |
| 2026-10-23 | 需求 | 023 教材口径校准完成（第二/三/十一章）：`descriptive_stats`、`reference_range`、相关强度与因果提示、回归方差分析表 | 评估报告 G0/G3 缺口；教材核对发现描述指标缺标准差、参考值范围完全缺失 |
| 2026-10-23 | 需求 | 022 结果解释与交付后答疑分流完成 | 产品定位要求「交付图表与解释建议」，评估报告 P0-6；旧实现交付只有表/图/策略链 |
| 2026-10-23 | 结构 | 022–029 全部成果按 4 个自包含提交入库（代码+测试 / spec 归档 / 文档 / 协作计划） | 此前仅 2 次提交且停在 spec 021；`registry.py`/`methods.py`/`service.py` 被多 spec 共改，按 spec 拆会让中间提交不可构建 |
| 2026-10-23 | 结构 | 新增 `EstimandSpec`/`IntercurrentEvent` 契约与 `sap_status_of` 纯函数；`sap_status` 不进模型字段，由 service 计算后写入事件 | 防止模型或前端伪造「确证性」状态，状态只允许一个来源 |
| 2026-10-23 | 结构 | 新增 `stats/impute.py`；`execute_step` 注入内部保留键 `_artifact_dir` 供 handler 落盘；service 扫描 `imputed_dataset` 并新增 `dataset_added` 事件 | pipeline 的 `execute_step` 不传目录给 handler，需一个受控落盘通道；复用 `data_profile` 会自动切换 active，打断用户当前工作区 |
| 2026-10-23 | 结构 | 插补数据集以 `<原名>（MICE 插补）` 注册到 `session.datasets`，`active_dataset_id` 保持不变；前端标签页加「已插补」角标与标准误警示 | 用户需要对照原始表与插补表，自动切换会丢失上下文 |
| 2026-10-23 | 结构 | 新增 `stats/survival.py`；`ChartType` 与 `CHART_TYPES` 增 `survival_curve`；补绘图路径传入 `result` | `inference.py` 已约 700 行；补绘图原先不传 result，生存曲线在 plot_later 后会是空图 |
| 2026-10-23 | 结构 | 四种事后比较并入 `anova.correction`（snk/tukey/dunnett/lsd/scheffe/holm/bonferroni）；Kruskal 路径忽略参数事后退回 Dunn | 共用同一次 ANOVA 的 MS误差 与 df误差，拆成独立工具会重复计算并使用错误的误差项 |
| 2026-10-23 | 结构 | 新增 `stats/inference.py`（单样本/区组/析因/重复测量/McNemar/样本量）与 `stats/notes.py`（教材口径文案单一源） | `stats/methods.py` 已约 900 行，继续膨胀会失控；口径文案集中才可整体评审 |
| 2026-10-23 | 结构 | 从 1009 例基线数据派生固定夹具 `backend/tests/fixtures/`，新增 `scripts/smoke_baseline.py` 全量冒烟（不入 CI） | 真实规模暴露正态判定缺陷；全链路（画像+描述+ANOVA+卡方）<0.3s |
| 2026-10-23 | 结构 | 新增 `descriptive_stats`（分布四态判定 + 推荐表达）与 `reference_range`（正态/百分位/对数正态），`describe` 保持七列不变 | 教材 §2/§3 要求按分布形态选指标；独立成工具避免波及画像、导出与既有断言 |
| 2026-10-23 | 规范 | 能力披露契约：每条 planned 必须写明「未实现/不支持」范围，且 name 不得与注册表键重名 | `multiplicity_control` 曾写「Holm/Dunnett 未实现」而 025 已实现；模糊清单不会主动提醒作者回头改 |
| 2026-10-23 | 规范 | caveat 按 `sap_status` 二选一（已声明/探索性），先剔除两条固定文案再追加；新增前后端文案红线扫描测试 | 两条固定文案并列会互相稀释；「五要素齐全」不等于事前注册，不得用 pre-specified 或确证性描述本系统产出 |
| 2026-10-23 | 规范 | 新增 `ChartType == CHART_TYPES` 一致性测试 | 本次真实漏改 `ChartType`，导致 `PlanStep` 在 pydantic 阶段被拒（与 023 的 `MethodType` 漏改同类） |
| 2026-10-23 | 规范 | `capabilities.planned` 移除 `survival_analysis`，改列 `competing_risk`（Fine–Gray） | 原描述写「需引入 lifelines」错误，`statsmodels.PHReg` 已足够；竞争风险教材 0 处提及，标 planned |
| 2026-10-23 | 规范 | 教材未给公式的方法必须在 `method_note` 与 `docs/statistics-methods.md` 标注外部依据 | 七项均无教材公式，不能冒充教材口径；读者需知道结论按哪套标准得出 |
| 2026-10-23 | 规范 | 两独立样本方差齐性改 F 检验、α=0.10；配对设计**不做**方差齐性检验 | 教材 §7 公式 7-6 与注意事项 2；配对设计的前提是差值正态而非两组方差齐 |
| 2026-10-23 | 规范 | 率的分子必须显式：`chi_square` 新增 `event_value`，输出 `rate_column` 标注 | 列联表列顺序由字符串排序决定（「无效」排在「有效」前），真实数据会把有效率算成无效率 |
| 2026-10-23 | 规范 | 大样本（n≥500）正态判定以偏度为主；单一取值占比 >50% 判偏态 | 1009 例数据中年龄偏度 −0.16 但 Shapiro P=4.6e-07，旧规则误判为偏态并推荐中位数 |
| 2026-10-23 | 规范 | 均值差 CI 改 t 临界值（合并方差/Welch/配对自由度）；配对检验改检差值并降级 Wilcoxon；非参数改中位数差 + 2000 次 bootstrap | 旧实现固定用 1.96，n=6/组时区间偏窄约 15%；配对设计与非参数路径均用错前提 |
| 2026-10-23 | 规范 | `MethodType` 必须等于注册表键 ∪ 别名，新增 `backend/tests/test_method_contract.py` | 漏改枚举会让模型输出在 pydantic 阶段被拒，不会走到宿主 `validate_step` 的友好提示 |
| 2026-10-23 | 规范 | 因果断言按「主语+因果动词」硬拦截并豁免否定语境；数值走软标（四舍五入与 `p<0.001` 放行） | 医学结论不能由模型自由断言因果；硬拦数值会因四舍五入大量误伤，角标失去意义 |
| 2026-10-23 | 规范 | 交付态路由归状态机（`SessionStatus.DELIVERED`），不新增 `revise_mode` 字典 | Owner 划分：前端不决定服务端路由；旧实现交付后追问会误触发重新出方案 |
| 2026-10-23 | 选型 | 不新增 `estimand_update` WS 事件，修改五要素走现有 supplement/revise 通道重出方案 | 避免部分更新语义与并发冲突，与该卡片现有交互一致 |
| 2026-10-23 | 选型 | `scikit-learn>=1.3` 作为**必需依赖**（非可选 extra）；`IterativeImputer` 需显式 `from sklearn.experimental import enable_iterative_imputer` | 项目首个真正新增的运行时依赖；MICE 是 P0 能力，降级分支会让「缺失路径」形同虚设 |
| 2026-10-23 | 选型 | Dunnett 采用 `scipy.stats.dunnett`，`backend/pyproject.toml` 的 scipy 下限由 1.12 提到 1.14 | 避免自实现多元 t 数值积分；版本下限若不同步，新环境安装后要到运行时才暴露 AttributeError |
| 2026-10-23 | 选型 | Dunnett 固定 `random_state=np.random.default_rng(20261023)` | 实测同一数据两次调用 p 值差约 3%（1.96e-4 vs 2.52e-4），不固定随机源则「结果可复现」这条硬门不成立 |
| 2026-10-23 | 环境 | `.gitignore` 忽略 `docs/*.pdf`（教材 31MB 不入库） | 仓库体积与 clone 成本；PDF 仅本地参考，测试不依赖 |
| 2026-10-23 | 环境 | 安装 scikit-learn 1.9.1（清华镜像），`pyproject.toml` dependencies 同步 | 直连 PyPI 不稳定；CI 依赖由 pyproject 自动安装，无需改 workflow |
### 2026-10-21

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|

| 2026-10-21 | 结构 | 新增错误码 `PROTOCOL_UNSUPPORTED` | 未知消息类型曾返回 `INVALID_PLAN`，语义错误、前端无法区分 |
| 2026-10-21 | 规范 | 019 全链路测试体系：四层金字塔（方法/编排/契约/前端）+ 数据根请求期解析 + `conftest` 自动清场 | 测试曾写真实 `backend/data` 并依赖 `.env`，导致污染与不可重复 |
| 2026-10-21 | 规范 | 020 正确性护栏：整数测量变量按「列名词元/中文子串 + 跨度规则」判 continuous，0/1 与评分分级保持 ordinal | `age=[25,31,42]` 曾被推断为 ordinal，参数检验被默认降级、功效损失 |
| 2026-10-21 | 规范 | Logistic 分离三重检测（未收敛 / max\|β\|≥15 / OR 非有限）拒绝输出 | 极端 CI 会作为结果下发（评估报告 P0-4）；Firth 惩罚仍待实现 |
| 2026-10-21 | 环境 | CI 三作业（backend/frontend/e2e）+ 后端覆盖率门槛 83% + 本地镜像 `scripts/ci.sh` | 无门槛合并会让测试与 E2E 形同虚设；本地镜像保证与远端一致 |
| 2026-10-21 | 迁移 | `git init` + 首次提交 `316b103` 并推送 main | 接入 GitHub Actions 的前提（spec 021） |
### 2026-10-19

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|

| 2026-10-19 | 结构 | 会话/工作区语义重构：会话 Tab = 与 LLM 交互，工作区 Tab = 数据画像/统计表/图表；表格交付进工作区并支持 CSV/XLSX 导出 | 用户心智模型「上传→看数据」与聊天流混杂，交付物散落 |
| 2026-10-19 | 结构 | 015/016/017 类型系统：四类变量类型（continuous/ordinal/categorical/index）+ `type_review` 前置门控 + 类型驱动方法与图表映射 | 类型决定可用检验，不能由模型猜；误判会静默降级检验 |
| 2026-10-19 | 结构 | 012/013/014 多工作区 + 工具槽位化（task/slots/applicability）+ 出图前确认（chart_config → chart_choice） | 多表场景需要独立工作区；出图不可控且拼图需求未被满足 |
| 2026-10-19 | 结构 | 018 会话×工作区绑定（一会话一表、消息按会话隔离），修复事件路由 stale closure | 多会话并行时消息串台，思考折叠状态失效 |
### 2026-10-18

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|

| 2026-10-18 | 结构 | ToolSpec 单一真相源（参数契约/图表声明/实现集中），`executor` 按注册表派发 + 单步失败隔离 | `hypothesis_test` 缺参 KeyError 暴露契约与实现分散；新增方法必须只改一处 |
| 2026-10-18 | 结构 | 010 实时交互：错误码体系 + 模型单请求流式 + 会话任务化（中断/继续）+ 执行步骤进度 | 长任务需要可中断与可见进度；错误需要可区分语义 |
| 2026-10-18 | 结构 | 011 选项与能力披露：`AnalysisPlan.options`（宿主保证 confirm/唯一/≤4）+ `GET /capabilities` | 模型不能自由发明方法；前端需要知道可用方法与参数 |
| 2026-10-18 | 规范 | 检验策略链（正态性→Levene→失衡→最优/次优）+ 显著性规范（α/星号/Holm 校正/多重提醒） | 检验选择必须可解释、可追溯，不能只给最终 p 值 |
### 2026-10-17

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-10-17 | 结构 | 001 后端骨架：FastAPI + `/health` + 会话创建 + Agently OpenAICompatible 配置 + 模拟模型结构化契约 | 垂直切片推进，5 项测试先绿 |
| 2026-10-17 | 结构 | 002 数据解析与画像：CSV/xlsx 解析、类型推断、缺失/数值/类别画像、TableProfile 序列化 | 画像是一切分析与讨论的输入，必须先稳定 |
| 2026-10-17 | 结构 | 003 讨论智能体：AnalysisPlan 契约（方法与图表枚举、宿主校验目标列 ⊆ 画像列名）、画像注入 info、修正意见注入 instruct | 模型产出的方案必须可被宿主校验，否则无法进入执行 |
| 2026-10-17 | 结构 | 004 pipeline 引擎：五类步骤 + 六类图表 PNG artifact + ExecutionReport；matplotlib 用 Agg 后端 | 无 GUI 环境需要确定性出图；报告作为前后端共同契约 |
| 2026-10-17 | 结构 | 005 分析工作流：TriggerFlow 编排（review `pause_for` 等待审阅、`RE_EXECUTE` 图可见回边）+ LocalRecordStore 按 session_id 查询 | 修正回边必须在图里可见，否则无法解释状态流转 |
| 2026-10-17 | 结构 | 006 会话编排 API：REST 上传+画像、SessionService 编排（chat/confirm/review）、WS 薄封装、修正意见注入再讨论 | 前端只能通过薄封装接入，业务逻辑集中在 service |
| 2026-10-17 | 结构 | 007 前端 SPA：Vite5 + React18 + TS + Tailwind3 双栏工作台（聊天流/数据图表工作区、方案卡、审阅卡、图表放大下载） | 该 spec 无独立文档留存，交付内容以代码与 components 为准 |
| 2026-10-17 | 结构 | 008 一键启动器 `python main.py`：dev 双子进程 + 进程组管理，`--prod` 构建后单端口托管 SPA | 降低启动成本；dev/prod 双模式真实冒烟通过 |
| 2026-10-17 | 规范 | spec 生命周期 draft/designing/implementing/done/archived，用目录移动表达流转 | 避免口头状态；进入 implementing 前必须行为可测 |
| 2026-10-17 | 规范 | Owner 划分：模型只做语义决策，schema 校验/枚举/算术/副作用归宿主；禁止自定义状态存储、用正则做语义判断、全量数据塞 prompt | 保证可测性与可复现；模型输出不能直接进数值链路 |
| 2026-10-17 | 选型 | Agently + FastAPI + React SPA + mamba（Sta 环境） | Agently 的 TriggerFlow/LocalRecordStore 原生能力与 Owner 划分契合；mamba 解决 C 依赖与 CJK 字体 |
| 2026-10-17 | 环境 | pip 安装走清华镜像 | 直连 PyPI 不稳定，安装频繁失败 |
| 2026-10-17 | 环境 | 修复 `.env` 未自动加载、httpx timeout 缺 write/pool、`set_settings(model)` 整体替换插件命名空间三个缺陷 | 真实模型冒烟暴露；后续写入 CODEBUDDY 作为禁止项（必须逐键点路径合并） |

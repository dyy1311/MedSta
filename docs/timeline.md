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

### 2026-11-16

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-11-17 | 需求 | 040 分析报告导出：`medsta/reporting.py` 中间表示（ReportDocument/Section）——风格（学术：方法学章节+表/图连续编号+教材口径 / 轻量：紧凑要点）在构建层、格式（md 字符串 / docx python-docx 三线表+嵌入图 / pdf reportlab）在渲染层正交；`GET /report/{sid}?style=&format=&report_id=`（404/400/历史报告寻址；/report 纳入鉴权与 SPA 豁免）；PDF 中文字体策略——优先系统 TrueType .ttf，回退 reportlab 内置 Adobe CID STSong-Light（本机 Noto 为 CFF 轮廓 TTC 不支持）；前端「执行产出」区导出控件（风格/格式下拉+下载链接，默认学术风 docx）；pyproject 增 python-docx/reportlab | 用户确认：课题组共享部署、报告双风格三格式随用户选择——闭合「数据→分析→交付物」链路；后端 467 passed（+10）、前端 78 passed；多用户化列为 041 |
| 2026-11-17 | 规范 | 039 工程质量收尾：库代码 print→logging（ws/service 等 10 处；launcher CLI 豁免）+ `test_no_print_statements` 守护；pyproject 配置 ruff（line-length 120，E/F/W/I/UP；UP042 禁用因仓库依赖 str(Enum) 的 f-string 语义）与宽松 mypy（ignore_missing_imports），双工具对 src+tests 清零并纳入 ci.sh（Backend lint / type check 两个新步骤）；前端 ErrorBoundary（class 组件 + 可注入 fallback + 重载按钮，main.tsx 挂 AppWithBoundary）；期间顺带修正 plotting `_annotate_pairwise` positions 签名误标（实为组名列表） | 审查遗留工程质量项清零；CI 从「仅测试」升级为 lint+类型+测试三道门；后端 457 passed、前端 77 passed |
| 2026-11-17 | 需求 | 038 可选单令牌鉴权：env `MEDSTA_AUTH_TOKEN` 开关（未配置时零行为变化，既有 450 用例零改动全绿即证明）；配置后 HTTP 全路由（/health 豁免）要求 X-Auth-Token 或 Bearer，WS 升级要求 `?token=`（错则 accept 后 close 4401），SPA fallback 与静态 /data 同受保护；CORS 仅在鉴权关闭时保留 `*`；.env.example 与 README 补配置说明 | 审查遗留 A2（零鉴权+CORS *+0.0.0.0）：单机内用可接受，局域网/公网部署前需可开启；后端 456 passed（+6） |
| 2026-11-17 | 需求 | 037 工作链增强二期：链间管道（impute 产出 `_next_frame` 内部键，executor 经 `execute_step_with_frame` 替换后续步骤 df；registry 出口 `execute_step` 剥离该键维持严格 JSON 硬门）；装配器按 accepts+列类型置灰不适用工具（无类型信息不置灰）；链含 impute 显示管道提示；模板导出 `GET /templates/{name}/export` 与导入 `POST /templates/import`（重名 409，overwrite 覆盖），前端 FileReader 读取（jsdom 无 file.text） | 033 产品闭环：插补→分析必须拆两次执行；模板需跨用户/机器交换；后端 450 passed、前端 75 passed |
| 2026-11-16 | 需求 | 036 会话消息流完整回放（035 增强）：用户动作（chat/确认/审阅/选项/类型确认/装配链等 9 类）在 `service.handle` 入口统一记入事件流为 `<event>_user` 帧（占 seq、不实时广播、内容精简只含 content/decision/option_id）；重连回放自然包含用户帧，前端按 `*_user` 后缀渲染用户气泡（review_user(revise) 渲染修正意见），刷新/重启后聊天上下文完整重建；回放帧经 ws 裸发通道不写回事件流（幂等，回放区间帧内容与顺序不变）；`events.jsonl` 增加轮转（超阈值保留尾部一半，seq 内存计数器不回退） | 035 明确的后续项：用户自己发的消息不在事件流中，刷新/重启后聊天上下文断裂；后端 444 passed、前端 72 passed |
| 2026-11-16 | 需求 | 统计层三处中危修复（审查遗留）：M8 Schoenfeld PH 检查按事件掩码排除删失行（statsmodels 0.14 残差删失行置 0，此前伪 0 与删失大时间稀释 Spearman rho、PH 违反检出率下降）；M19 MICE 插补间方差只在缺失格计算（此前观测格方差恒 0 计入均值，按缺失占比系统性低估）；M20 插补产物按 `_step_index` 命名 `imputed_step_{i}.csv`（此前固定名，同计划两次插补互相覆盖）；registry `execute_step` 注入 `_step_index` 内部键 | 代码审查遗留 P2 正确性尾差；确定性测试守护（FakeModel 残差 / FakeImputer 确定性填充 / 双产物共存断言）；后端 441 passed |
| 2026-11-16 | 需求 | 035 WS 断线重连 + 历史回放：出站帧经 `EventLog` 注入单调 `seq` 并追加落盘 `events.jsonl`（落盘失败降级仅投递）；`resume` 扩展 `last_seq` 缺口补发（原帧原 seq 绕过包装，不重复投递），后端重启后 seq 续接回放；前端 `connectSession` 非手动断线自动重连（指数退避 1s→2s→…上限 10s，成功后重置）+ 重连携带 `resume`+`last_seq` + 头部连接状态徽标（已连接/重连中呼吸动画） | 审查 H2：断线后消息静默丢弃界面卡死；032 快照仅恢复状态不恢复事件流；入站用户消息回放不做（备注后续） |
| 2026-11-16 | 需求 | 034 工作链模板保存与复用：`session/templates.py` TemplateStore（`data_root/templates/*.json` 原子写、同名覆盖、损坏文件跳过）+ `GET/PUT/DELETE /templates[/{name}]`（模板名宿主校验防路径穿越、steps 方法注册校验）；装配 Tab 新增「我的工作链」区（命名保存/一键载入/删除，跨会话复用）；目标列快捷勾选（全部数值列/全部类别列/全选/清空，App 传入 columnTypes）；`tool_catalog` 输出 `accepts`（列类型预过滤数据基础，硬过滤留后续） | 033 产品闭环补全：装配成果此前一次性，无法沉淀为可复用资产；后端 434 passed、前端 67 passed |
| 2026-11-16 | 需求 | 三区布局重构 + 结果表格化：桌面（lg+）三栏并排 + 两枚拖拽手柄实时调宽（会话 280–640px / 装配 260–560px，useIsDesktop 响应式）；窄屏回归 Tab 单栏切换（修复 lg~xl 区间工作区恒显、xl 以上 Tab 全失效的断点类混乱）；新增 `ResultTable` 通用「结果 JSON → 表格」渲染器——审阅卡「结果数据」默认展开表格（原始 JSON 折叠后备），工作区对无专用表格步骤渲染「结果数据」卡 | 用户报告三缺陷：选项卡切换失败（断点类互相覆盖）、三区拖拽未实现、部分工具结果只有原始 JSON 无表格；`ResultTable` 跳过 method_note/strategy 元键，标量→指标表、对象数组→动态列子表 |
| 2026-11-16 | 需求 | 033 原子统计工作链完成（产品定位调整：模型不灌管线）：WS `run_chain` 手动装配执行通道（宿主 `validate_plan` 硬校验、跳过出图确认暂停、零模型参与可执行）；前端「工具装配」Tab（按分类选工具、按 ToolSpec 动态参数表单、目标列/图表选择、工作链上移/下移/删除、模型方案一键导入）；交付态可装配新链，执行中被 SESSION_BUSY 拒绝 | 用户主权要求：每个统计分析指令工具化，模型只提建议，用户自行装配确认后执行；registry 22 个 ToolSpec 即原子单位 |
| 2026-11-16 | 环境 | 安装三个前端技能到 `~/.codebuddy/skills/`：`frontend-dev`（高级 UI+动效）、`awesome-design-md`（54 个品牌设计系统模板）、`frontend-design-guidelines`（SkillHub 下载量 11.3K 的反 AI 模板化设计指导） | 用户要求联网检索并安装高分前端/美化技能 |
| 2026-11-16 | 需求 | 前端视觉升级（美学方向：精密仪器/Refined，参考 Linear 层次纪律）：自托管 Space Grotesk（display/数字排印）+ 全局 `tabular-nums` 数字等宽；头部深度渐变（双色光晕+底边微光）；页面「坐标纸」底纹；阴影四级体系（xs/sm/card/hover/pop）；细滚动条、品牌选区色、统一 focus-visible 环；执行进度不定态 shimmer；统计表表头分层+行 hover、卡片 hover 提升 | skill 指导：commit to a palette、memorable element、避免 AI 默认扁平观感；统计工具核心可读性=数字等宽对齐；截图验证通过 |
| 2026-11-16 | 规范 | JSON 输出硬门：`tests/test_json_contract.py` 逐工具采样（22 工具全覆盖），`execute_step` 出口必须通过 `json.dumps(allow_nan=False)`；新增工具不同时登记采样无法合入（覆盖性测试守护） | 用户硬要求「所有分析数据输出为 json」；NaN/Inf/numpy 类型均为硬失败 |
| 2026-11-16 | 需求 | 导出与登记：表格导出新增 `format=json`（meta/table/result 完整输出）；图导出新增 JPG/PDF/TIF（按需重渲染，与 PNG 并存）；`docs/tools.md` 登记全部统计工具与作图类型并由 `test_tools_md_matches_registry` 双向守护；前端表格行加 JSON 下载、图卡加 JPG/PDF/TIF 下载 | 用户要求：前端只呈现表格/图，下载提供 JSON/CSV/XLSX/PDF/TIF/JPG；工具登记文档化 |
| 2026-11-16 | 需求 | 032 会话持久化完成：`session/persistence.py` SessionStore（JSON+原子写），上传/类型确认/方案落定/报告产出/交付/切工作区 6 个落盘点，`create_app` 启动恢复（DataFrame 从数据文件重建+列类型重放），`resume` 还原审阅/交付态；`executing` 快照恢复降级 `discussing` | TO_DO P1-1 前半；此前会话只存内存重启即丢，是内部日常使用最痛的基础设施缺口；快照不含 DataFrame 数据（体积可控），为 033 断线重连/回放提供数据源 |
| 2026-11-16 | 选型 | 会话快照存 JSON+原子写（tmp+`os.replace`）而非 SQLite：会话量小、结构松散、无并发查询需求；落盘先于送达（delivered/type_confirmed 帧发出前先 persist），堵「accept 后立即断连丢失交付态」 | 若 033 需要事件日志追加写再评估升级 |
| 2026-11-16 | 需求 | 历史报告可寻址导出：执行报告注入 `report_id`，`GET /export/{sid}/{step}?report_id=` 定位历史报告（缺省最新），前端导出链接带参；此前 workspace 历史报告的导出链接全部指向最新报告（M2） | 前后端契约错配：用户对比多份报告时导出的不是看到的那份 |
| 2026-11-16 | 需求 | 两处健壮性修复：文本列被改为连续/等级时画像按 `to_numeric` 兜底（此前 TypeError 穿透 500/断连，S5）；图表渲染失败与统计计算隔离（`chart_error` 字段，此前整步 failed 连带丢弃已算出的结果，E1） | 代码审查遗留 P2 项；均为用户一次操作即可触发的可见故障 |

### 2026-10-24

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-10-24 | 需求 | 统计正确性七处修复：Breslow 方差补乘 w²、RMST 组间统一 tau=各组最大随访最小值、`mcnemar_test` 加入分类列校验豁免、AUC 改平均秩（rankdata）、配对 Wilcoxon bootstrap 改差值重抽样、Fisher 路径补算 Cramér's V（`effect_chi2`）、卡方内嵌表星号在 attach_significance 后读取 | 代码审查实测缺陷：Breslow χ² 被放大致假阳性、tau 不可比则 RMST 差无效、McNemar 对真实分类文本被 INSUFFICIENT_DATA 硬拒、并列预测值 AUC 系统性偏差、独立重抽样破坏配对结构、Fisher 路径效应量恒 0、星号恒 ns；修复后后端 382 passed |
| 2026-10-24 | 需求 | 安全边界三处收紧：SPA catch-all 加 resolve 前缀校验堵路径穿越、CSV/XLSX 导出对 `= + - @` 前缀文本单元格转义、上传加 50MB 限额（超限 413 并清理临时文件） | 审查实测 `GET /..%2F..%2Fetc%2Fpasswd` 可读项目外文件、`GET /.env` 可泄漏密钥；导出件在 Excel 打开可触发公式执行；上传无限制为 DoS 零门槛 |
| 2026-10-24 | 规范 | 编排契约升级：`manager.transition` 改为转移表强约束（非法转移抛 `InvalidStateTransition` → `PROTOCOL_UNSUPPORTED` 错误帧）；新增 `SESSION_BUSY` 错误码与同会话忙锁（chat/答疑并发拒绝）；WS 循环三层兜底（非 JSON/非对象/内部异常回错误帧不断连）；统计执行移入 `asyncio.to_thread`（进度回调经 `call_soon_threadsafe` 回主循环）；审阅超时改只对执行完成后计时，超时取消工作流并清理残留执行 | 审查发现：状态机为无条件赋值可 DELIVERED 重跑旧方案、执行同步阻塞全部 WS 会话（实测心跳停滞）、同会话无忙锁任务槽位互踩、非 JSON 帧直接断连；决策记录见 `docs/design-notes.md` §4 |
| 2026-10-24 | 选型 | `matplotlib>=3.8` 提升至 `>=3.9` | `plotting.py:131` 使用 3.9 引入的 `boxplot(tick_labels=)`，3.8 下箱线图 TypeError；声明与实现不一致 |
| 2026-10-24 | 需求 | 前端 `plan` 事件透传 `estimand`/`sap_status` 两字段并补 App 层集成测试 | 029 后端已下发但 App 层 emit 丢弃，方案卡恒显「探索性分析」，估计目标面板实际不可见；前端 52 passed |

### 2026-10-23

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|

| 2026-10-23 | 需求 | 031 文档体系建成：`architecture.md` 三张 Mermaid 图（分层架构 / 统计策略选择 / 执行流程）+ `product-guide.md` 产品说明，README 瘦身为入口 | 架构与流程此前只存在于代码与口口相传；README 长期停在「12 类方法 / 200 项」 |
| 2026-10-23 | 需求 | 030 阶段评估与 P0 修复完成：`evaluation-report.md` 重写为 029 基线（含 019→029 六维度对比），修正 `competing_risk`/`multiplicity_control` 滞后描述，022–029 成果一次性入库 | 评估发现「八个 spec 无任何提交」与「planned 描述滞后」两项 P0 风险；报告综合分 7.4 → 7.9 |
| 2026-10-23 | 需求 | 029 Estimand/SAP 完成：`AnalysisPlan` 增估计目标五要素（人口/变量/处理/伴发事件+策略/汇总指标），`plan` 事件下发 `estimand` 与 `sap_status`，方案卡折叠展示并标「已声明估计目标」或「探索性分析」 | 教材对 Estimand/SAP 0 覆盖，依据 ICH E9(R1)；方案只说「用什么方法」不说「回答什么问题」 |
| 2026-10-23 | 需求 | 028 缺失数据路径完成：`missing_report` 升级为缺失模式诊断（univariate/monotonic/arbitrary + 分组差异提示 + 阈值警告），新增 `impute`（MICE 20 次取均值 + 插补间方差、median/mean/LOCF 仅敏感性、delta 扫描）并产出可继续分析的插补数据集 | 教材对缺失数据 0 覆盖，依据 Little & Rubin (2019)/van Buuren (2018)；此前只能报缺失率，无法处理 |
| 2026-10-23 | 需求 | 027 生存分析族完成：KM（含排序规则与 Greenwood SE）、中位生存期、风险人数表、log-rank/Breslow、Cox（HR/CI/LR/Wald/Score）、Schoenfeld PH 检查、RMST，新增 `survival_curve` 图表 | 教材第十四章存在但 024/025 两轮误判为「无」，本轮 `grep` 关键词核实后按教材口径实现；删失资料无法用横断面方法处理 |
| 2026-10-23 | 需求 | 025 事后比较与设计类方法完成：Tukey/Dunnett/LSD-t/Schéffé 并入 `anova.correction`；新增 `factorial_anova`、`repeated_measures_anova`、`sample_size` | 教材仅在表 8-9 列名称、在练习题与设计章节提设计类型、检验效能只有 1−β 概念，均无公式；用户要求补全 |
| 2026-10-23 | 需求 | 024 第六至十章口径完成：新增单样本检验、随机区组方差分析、配对 McNemar；ANOVA 事后改 SNK-q、四格表三档、多样本率 χ² 分割、Kendall τ | 复核教材目录发现第六至十章正文存在，此前只读了第二/三/十一章 |
| 2026-10-23 | 需求 | 023 教材口径校准完成（第二/三/十一章）：`descriptive_stats`、`reference_range`、相关强度与因果提示、回归方差分析表 | 评估报告 G0/G3 缺口；教材核对发现描述指标缺标准差、参考值范围完全缺失 |
| 2026-10-23 | 需求 | 022 结果解释与交付后答疑分流完成 | 产品定位要求「交付图表与解释建议」，评估报告 P0-6；旧实现交付只有表/图/策略链 |
| 2026-10-23 | 结构 | 三张图集中 `docs/architecture.md` 单一来源，`product-guide` 与 `statistics-methods` 只链接不复制；`project-profile` 工作流改为引用图 3 | 同一张图存两处必然漂移，漂移的架构图比没有更误导 |
| 2026-10-23 | 结构 | 022–029 全部成果按 4 个自包含提交入库（代码+测试 / spec 归档 / 文档 / 协作计划） | 此前仅 2 次提交且停在 spec 021；`registry.py`/`methods.py`/`service.py` 被多 spec 共改，按 spec 拆会让中间提交不可构建 |
| 2026-10-23 | 结构 | 新增 `EstimandSpec`/`IntercurrentEvent` 契约与 `sap_status_of` 纯函数；`sap_status` 不进模型字段，由 service 计算后写入事件 | 防止模型或前端伪造「确证性」状态，状态只允许一个来源 |
| 2026-10-23 | 结构 | 新增 `stats/impute.py`；`execute_step` 注入内部保留键 `_artifact_dir` 供 handler 落盘；service 扫描 `imputed_dataset` 并新增 `dataset_added` 事件 | pipeline 的 `execute_step` 不传目录给 handler，需一个受控落盘通道；复用 `data_profile` 会自动切换 active，打断用户当前工作区 |
| 2026-10-23 | 结构 | 插补数据集以 `<原名>（MICE 插补）` 注册到 `session.datasets`，`active_dataset_id` 保持不变；前端标签页加「已插补」角标与标准误警示 | 用户需要对照原始表与插补表，自动切换会丢失上下文 |
| 2026-10-23 | 结构 | 新增 `stats/survival.py`；`ChartType` 与 `CHART_TYPES` 增 `survival_curve`；补绘图路径传入 `result` | `inference.py` 已约 700 行；补绘图原先不传 result，生存曲线在 plot_later 后会是空图 |
| 2026-10-23 | 结构 | 四种事后比较并入 `anova.correction`（snk/tukey/dunnett/lsd/scheffe/holm/bonferroni）；Kruskal 路径忽略参数事后退回 Dunn | 共用同一次 ANOVA 的 MS误差 与 df误差，拆成独立工具会重复计算并使用错误的误差项 |
| 2026-10-23 | 结构 | 新增 `stats/inference.py`（单样本/区组/析因/重复测量/McNemar/样本量）与 `stats/notes.py`（教材口径文案单一源） | `stats/methods.py` 已约 900 行，继续膨胀会失控；口径文案集中才可整体评审 |
| 2026-10-23 | 结构 | 从 1009 例基线数据派生固定夹具 `backend/tests/fixtures/`，新增 `scripts/smoke_baseline.py` 全量冒烟（不入 CI） | 真实规模暴露正态判定缺陷；全链路（画像+描述+ANOVA+卡方）<0.3s |
| 2026-10-23 | 结构 | 新增 `descriptive_stats`（分布四态判定 + 推荐表达）与 `reference_range`（正态/百分位/对数正态），`describe` 保持七列不变 | 教材 §2/§3 要求按分布形态选指标；独立成工具避免波及画像、导出与既有断言 |
| 2026-10-23 | 规范 | 新增 `test_docs_consistency.py` 六条断言：附录工具清单与注册表严格相等、README 禁具体计数、无死链、能力矩阵覆盖全工具、三图边数≥10、禁过期表述 | 文档无人守就会失真；把「与代码同源」变成可执行规则 |
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

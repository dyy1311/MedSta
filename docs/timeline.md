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

### 2026-11-21

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-11-21 | 规范 | 计划期条件必填：`anova.correction=dunnett` 缺 `control_group`、对照组名不在分组列中、`survival_analysis.method=logrank` 缺 `group_col`、`method=cox` 缺 `covariates`，一律 `MISSING_PARAM`/`INVALID_PARAM`，不再拖到运行期 `ValueError`。内置生存模板的 Cox 步补 `covariates=numeric_features`（只取数值列），避免推荐链在新硬门下被整步拿掉 | 上线前排查：这三类缺参此前要等工具函数抛错，方案卡无法在确认前指出缺什么 |
| 2026-11-21 | 需求 | 重跑/补图与首次执行使用同一张表：`_input_frame` 只重放 `FRAME_METHODS`（impute、dedupe、filter_rows、standardize、bin_column、winsorize）的 `_next_frame`，`_rerun_from` 对每个节点 `_mark_node`（成功清掉旧失败原因）。回归遇到类别自变量时点名列与非数值个数；`render_combined` 不足 2 张图直接拒绝；饼图改 `tab20`。前端：`*_user` 回放与本地气泡按文案合并（amend 帧带 `index`），补绘图按钮用 ref 挡住连点 | 手册复审记下的两处静默错分析，以及统计边界和重连重复气泡 |

### 2026-11-20

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-11-20 | 需求 | 类型确认体验三件套（用户截图反馈）：① 「AI 确认类型」点击后进入加载态——按钮转 `正在分析列含义…` + spinner + `aria-busy`，下方给出「模型正在逐列判断语义类型（表越大越慢）」说明，结果/错误/90s 超时三路复位（此前点完毫无反馈，用户以为没生效）；② 类型变更的**会话↔工作台同步**：`PATCH .../columns` 增加 `source`（manual/ai）并广播 `type_confirmed`（含 `updated` 列名与最新 profile），会话区按来源生成可核对文案（`已采纳 AI 建议，更新「value」→ 数值-等级型` / `列类型已更新：…` / 类型敲定）；采纳后建议条按列消费、单列采纳也走批量端点（此前单列 PATCH 不广播 → 右栏变、左栏无记录）；③ 工作区模块卡可折叠：数据画像 / 统计表交付 / 结果数据 / 执行产出 四块独立折叠（默认展开，`aria-expanded` + 方向箭头），表格交付块加 `data-testid=table-delivery` 便于定位 | 用户反馈「点 AI 类型确认后没有任何提示」「工作台更新后会话没有同步」「模块卡想收起」；前端 116 passed（新增 `App.typeSync.test.tsx` 5 项）、后端 553 passed + 1 skipped（新增 `test_type_sync.py` 5 项）、E2E 2 passed |
| 2026-11-20 | 需求 | 修复「刷新后工作区与会话区断开」（用户实测，RED→GREEN 7 项）：① 新增 `GET /sessions/{sid}/workspace` 工作区快照（`datasets[{dataset_id,name,profile,type_confirmed,active}]` + `active_dataset_id` + 当前 `report`/`report_id`；归属校验沿用鉴权中间件，他人 404）；② 前端进入会话即拉快照，与 WS 回放按 `dataset_id` 增量合并，`upsertReport` 改为按 `report_id` 去重（回放重放历史 `review_request` 会堆出重复统计表）；③ `WorkspaceTab` 增必填 `sessionId`，标签/计数/选择只取当前会话的数据集——此前全局平面数组 + `activeWorkspaceId` 残留，切会话后右栏仍显示上一个会话的表与报告；④ 切到无数据集的会话时清空 `activeWorkspaceId`（不再回落旧值）；⑤ 刷新后自动回到上次会话（`localStorage.medsta_active_session`，失效则取列表首个）——此前 `activeChatId` 恒为 null，左右两栏都是空态；⑥ 报告先于画像到达时先挂 `pending-{sid}` 占位工作区，快照到达后迁移报告并删占位；⑦ `resumed` 帧按服务端 `stage` 校正 `phase`：回放的历史 `progress` 帧会把界面永久卡在「执行中」（进程重启后任务早已结束），现在回到 `idle`/`delivered`/`executing` 三者之一 | 用户反馈：刷新后两侧不挂钩、左栏继续显示执行变动而右栏不动；根因是「右栏只能靠事件流重建 + 工作区无会话归属 + 无默认会话恢复」。后端 547 passed + 1 skipped、前端 111 passed（新增 `App.hydrate.test.tsx` 4 项）、E2E 2 passed（首个用例补「刷新后左右同源」断言） |
| 2026-11-20 | 需求 | 类型误用提示三处对齐（用户实测 `COLUMN_TYPE_MISMATCH`：把「是否手术」「手术方式」当目标列传给 group_compare/anova）：① 宿主校验 hint 精准化——目标列是类别型且该工具有 `group_param` 时，直接给可执行修法（`target_columns` 只放数值列 + 在 `params.group_column` 里选它），无分组参数的工具保持通用提示；② `tool_catalog` 下发 `group_param`，装配器勾选目标列时按 `accepts` 实时提示类型不匹配，并提供「一键设为分组列」（移出目标列 + 填入分组参数）；③ 错误卡把 `detail.issues` 渲染成结构化列表（步骤号 + 原因 + 修法），原始 JSON 退为二级折叠；④ 讨论 prompt 明确「类别列通常是分组/分层变量、不得进 target_columns」，与宿主校验互为兜底 | 用户贴出的 issues 显示 3 个步骤同因失败，仅提示「可用 chi_square」不足以指导修正；后端 558 passed + 1 skipped（`test_type_mapping` 新增 3 项）、前端 121 passed（ChainBuilder 2 项 + ErrorCard 2 项）、E2E 2 passed |
| 2026-11-20 | 需求 | 047 统计工作流编排（用户实测「一次性构造复杂管线并填对所有参数过于困难」）：① 方案以**流程图**交付——`PlanStep.depends_on` + `plan_flow()` 生成 `{nodes,edges,order,mermaid}`，节点必须是注册表工具，缺省依赖宿主补线性链；`plan` 事件带 `flow`，前端 `PlanFlowView` 渲染节点图（可展开参数、附 Mermaid 文本）；② **逐节点交付**——executor 每步回调 `on_step_result`，服务端下发 `step_result`（表格/图/错误），失败节点不阻断后续；③ **断点续接**——`retry_step {index,overrides}` 重跑该节点及下游、`amend_step {index,note}` 把「图 + 该节点 + 失败原因 + 用户补充 + 会话上下文」交给模型只重写这一个节点，宿主校验后就地替换并重跑；前端节点卡支持「重跑」与「让 AI 修正」；④ **会话上下文分层**——`SessionContextStore` 按 `owner → session` 管理（数据摘要/节点状态/失败原因/用户补充，`snapshot()` 长度受限），删除会话即释放；⑤ **内置统计 skills**——`agents/stats_skills.py` 提炼 SAMPL 报告规范、检验选择决策树与常见误用（12 条），宿主按关键词挑选并注入讨论/修正 prompt | 用户明确要求「流程图确认 → 逐节点执行 → 报错后补充信息接续」；后端 576 passed + 1 skipped（新增 test_flow_graph 7 项、test_step_delivery 6 项、test_session_context 5 项、test_stats_skills 5 项）、前端 129 passed（PlanFlow 3 项 + stepDelivery 5 项）、E2E 2 passed |
| 2026-11-20 | 需求 | 方案缺 rationale 的自动补全（用户实测：6 个步骤全部 `MISSING_PARAM` → `INVALID_PLAN`）：根因是 `_OUTPUT_FIELDS.steps` 的字段描述未列出 `rationale`（模型只看到 instruct 里一句话，偶发整份方案漏填），而宿主把「缺依据」当硬门拒绝——用户看到 6 条「缺少选择依据」却没有任何可改的入口。修复两道防线：① 输出契约显式声明 `rationale(str，必填)` 与 `depends_on(list[int]，可选)`；② 新增 `_ensure_rationales`：有步骤缺依据时自动发起一轮「只补依据」的请求（要求原样返回步骤序列、只填 rationale，宿主仅合并该字段，不动 method/targets/params），补完仍缺才按硬门拒绝（可解释性不降级）；前端方案卡对空依据显示「依据未提供（可让它补充说明）」 | 用户贴出的 6 条 MISSING_PARAM；后端 585 passed + 1 skipped（新增 `test_rationale_repair.py` 4 项：契约含 rational/补全成功/补全失败仍拦/齐全时不额外调模型）、前端 129 passed |
| 2026-11-20 | 需求 | 工作链推荐模板 + AI 一键匹配（048）：① `agents/chain_recipes.py` 内置 5 条按统计 skills 预设的流程（数据质量与基线 / 两组比较 / 多组 ANOVA+事后 / Logistic 影响因素 / 生存 KM+log-rank），节点全部取自注册表，列位置用占位语义（group/continuous_primary/time/event/binary_outcome/feature_list）；② **宿主筛候选 + 模型只在候选内选**：`candidates_for` 按列类型/组数/取值确定性筛候选，`ChainMatchAgent` 单次结构化请求做语义选择，`match_recipe` 复核候选合法性（候选外列直接丢弃）；模型不可用/失败回退规则匹配并标注 `matched[].by`；③ 匹配结果逐步 `validate_step` 硬校验，不合格步骤移除并给 warning（不产出必失败的推荐链）；④ 前端装配区新增「推荐流程」区块（一键匹配并载入）+ 步骤来源标签 + 「编辑」回填表单就地替换（人为修改保留）；接口 `GET /templates/builtin`、`POST /sessions/{sid}/chain/match` | 用户要求「按 skill 预设模板放进工作链搭建区作为默认推荐，并做 AI 一键匹配、保留人工修改」；后端 595 passed + 1 skipped（新增 `test_chain_recipes.py` 10 项）、前端 133 passed（新增 4 项）、E2E 2 passed |
| 2026-11-20 | 需求 | 参数驱动目标的工具被误判「至少需要一个目标列」（用户实测：步骤 7「是否手术的多因素 Logistic 回归」INVALID_PARAM）：根因三层——① `validate_step` 统一要求 `target_columns` 非空，而 `logistic_regression`/`regression` 的目标在 `params.target`、`survival_analysis` 在 `params.time_col`，填全参数也会被拒；② `_TASK_META` 规范化循环用 `ToolSpec(...)` 重建 spec 时**丢弃新字段**，注册处声明的 `target_param` 被静默抹掉（任何新增字段都会踩这个坑）；③ 内置模板 `quality_baseline` 里 `chi_square.comparison="rate"` 是非法取值。修复：`ToolSpec.target_param` 贯通（校验放行 + `tool_catalog` 下发 + 重建时保留）、`_NO_TARGET_TOOLS` 补 `missing_report`/`aggregate_table`、`_SLOT_META` 与真实参数名对齐（target/features）、模板非法 fixed 去除；新增守护测试「每条内置模板匹配后逐步骤通过硬校验」 | 后端 598 passed + 1 skipped（新增 test_type_mapping 2 项 + test_chain_recipes 1 项）、前端 133 passed、E2E 2 passed |
| 2026-11-20 | 需求 | 两处用户实测缺陷：① **多轮执行的旧图不清除**——右栏把 `reports`（每轮一份）里的图表全部摊平，三轮执行就出现三张同名直方图；改为**图表只展示最新一轮**（标题带「第 N 轮」），历史轮次在「历史轮次」折叠里按轮次汇总（统计表仍按轮次保留，可对照两次执行）；② **提交修正后没有反应**——`review revise` 只回「已记录修正意见」并等待用户再发一条，用户重复点「提交修正」会撞 `NO_ACTIVE_RUN`；改为后端**带意见的 revise 直接接续讨论**（先 `back_to_discussion`「正在按修正重新生成方案…」，再用 `_revision_notes` 自动 `_generate_plan`），前端提交即**锁定该审阅卡**（显示「修正意见已提交，正在按修正重新生成方案…」，不再发第二帧）；③ 顺带补「按类别出图」能力：`histogram` + `params.group_by` 时按组分面绘制（每组一个面板，一张产物；>6 组退回总体直方图），讨论 prompt 说明该填法 | 用户截图：3 张相同直方图 + 「修正意见：每个类别做一张图」后无反应、再点报 NO_ACTIVE_RUN；后端 601 passed + 1 skipped（新增 revise 自动重规划、分面直方图 2 项）、前端 136 passed（新增审阅卡锁定 2 项 + 图表按轮次 1 项）、E2E 2 passed |
| 2026-11-20 | 结构 | `docs/handbook.md` 复审后对齐 047/048 与前端审计：重写心跳（24 步，含 `plan.flow`、`step_result`、`retry_step`/`amend_step`）、后端新增「会话上下文分层」「推荐流程匹配」两节、Agent 侧新增「定点修正」「统计 skills 归属」两节（反模式表后移为 §4.10）、执行编排新增「节点级交付与断点续接」、前端改为五维分桶状态并补 `PlanFlowView`/`StepDeliveryCard`/结构化 ErrorCard/推荐流程、契约速查补 3 个事件与 2 个 REST 端点；**审查发现两处缺口写入 §5.6 已知边界**：① `_rerun_from` 不重放上游 impute/清洗的 `_next_frame`（重跑下游会用原始数据静默错分析）；② 重跑未 `_mark_node` 回写上下文（amend prompt 可能读到过期失败状态）；同步 `docs/architecture.md` 图 1/3 与所有权账本（新增 SessionContextStore / stats_skills / chain_recipes / chain_match 节点与节点级接续分支，修正图中工具数 22→28） | 项目在手册成稿后落地 047（流程图/节点交付/断点续接/上下文/skills）与 048（推荐流程 + AI 匹配），旧手册的 20 步心跳与「一次执行」交付粒度已失真；复审同时核对前端审计五项与 launcher 日志能力 |
| 2026-11-20 | 结构 | 新增 `docs/handbook.md` 教学版产品与实现手册（13 章）：三条铁律（模型只做语义决策/状态归宿主/单一真相源）→ 一次会话 20 步心跳 → 后端启动链与 `SessionService` 账本 → Agent 侧 Owner 判据与证据工程（`build_evidence`/因果硬门/句柄时序）→ 注册表校验顺序 → 前端四维分桶状态与事件映射 → 契约与错误码速查 → 四层测试与文档守护 → 8 个动手实验 + 排错表 + 代码地图；README 文档导航与 `product-guide.md` 相关文档增加入口，并顺手修掉两处过期计数表述（README「22 个工具清单」、产品说明指向 `#附录-a工具清单22` 的死锚点） | 用户需求：详细梳理整体架构、前后端实现与 agent 侧编排，形成教学形式的完备讲解手册；现有文档按产品/架构/统计/决策分工，缺一份把「为什么这样切 Owner、一次请求怎么走、改哪里」串起来的教学叙事 |
| 2026-11-20 | 规范 | 确立「REST 触发的状态变更必须走 `service.broadcast`」：`SessionService` 维护会话级发送器注册表（`attach_sender`/`detach_sender`，WS 连接建立注册、`finally` 摘除），`broadcast` 先 `EventLog.commit` 分配 seq 落盘、再逐个推送在线连接（发送失败即摘除）——因此**无连接时也留事件**，刷新回放可重建；前端不得用本地 emit 伪造同步。`patch_columns` 改为 async 路由，pandas 变更放 `run_in_threadpool` 避免阻塞事件循环 | 「工作台改了、会话区没记录」的根因是 REST 没有推送通道；本地 emit 会在多标签页/刷新后丢失，不属于可核对记录 |
| 2026-11-20 | 规范 | 会话恢复的单一真相源定稿：**持久状态走 REST 快照、实时增量走 WS 回放**，两者按 `dataset_id`/`report_id` 幂等合并；工作区（数据集标签、报告、激活项）一律以 `sessionId` 归属，禁止再出现跨会话共享的平面列表 | 事件流会按阈值轮转（035），`data_profile` 帧可能已被裁掉 → 只靠回放必然出现「左栏有、右栏空」；归属缺失会让切会话串台（静默错看数据） |
| 2026-11-20 | 规范 | 前端审计（状态机/WS 回放/竞态/内存泄漏/类型契约）五项收口：① `isActive` 改为实时读 `activeChatIdRef`（闭包里的会话 id 在事件到达瞬间可能已过期，旧会话帧会写坏当前会话显示）；② 类型契约补全 `PlanEvent.flow`、`WsEvent.step_result`、`PlanStep.depends_on`、`type_confirmed.updated/source`（此前用 `as unknown as` 绕过）；③ `retry_step_user`/`amend_step_user` 回放帧生成可读气泡（后端把 index/note 写进事件流，避免空气泡）；④ 建议超时定时器在卸载与删除会话时清理（内存泄漏）；⑤ **审计记录旁路化**：`_record` 写入失败（SQLite 锁/事件循环切换）只记 warning，不再把正常讨论变成 `EXECUTION_FAILED`——这正是一个偶发失败用例的真实根因（跨 loop Lock） | 审计实证：全量测试 3 次连跑由「2 次失败」变为「3 次全绿」；后端 576 passed、前端 129 passed |
| 2026-11-20 | 环境 | 新增残留清理入口 `scripts/clean_sessions.py`：服务在线时走 `GET /sessions` + `DELETE /sessions/{sid}`（内存与磁盘同步，避免只删磁盘留下幽灵会话），离线时删 `backend/data/sessions/*`（`--purge-records` 才动 SQLite 执行记录，需停服），并顺带清理 E2E 桩后端的 `/tmp/medsta-e2e-*`；`backend/tests/e2e_app.py` 启动时清理同前缀旧目录（Playwright 用 SIGTERM/SIGKILL 停 webServer，atexit 不保证执行）；**补隔离漏洞**：conftest 新增 autouse `_default_data_root_in_tmp`（重定向 `MEDSTA_DATA_ROOT`），堵住 9 处无参 `create_app()` 直接写真实 `backend/data`——此前每轮全量都留下 5 个 discussing 会话目录，dev 侧表现为「刷新后多出陌生会话」；`test_env_isolation.py::test_default_create_app_writes_into_tmp` 守护。本次清掉 214 个历史残留会话目录与 11 个 E2E 临时根 | 用户要求「每次操作/测试后把残留会话全部清除」：追溯发现残留有两条来源——手工/dev 运行，以及**测试自身的隔离缺口**（无参 app 走默认数据根）；不补机制只清理治不了根。后端 548 passed + 1 skipped、前端 111 passed、E2E 2 passed |
| 2026-11-20 | 环境 | 后端「报错」定位为**旧进程缺新路由**，并补可观测性：运行中的 dev 后端是 09:56 启动的（`uvicorn medsta.app:app --host 0.0.0.0 --port 8000`，无 `--reload`），openapi 里没有 `GET /sessions/{sid}/workspace`，实测返回 `{"detail":"Not Found"}` 404——前端新代码每次进入会话都请求该快照，于是浏览器/终端持续报错。配套改动：① `launcher` 新增 `--log-file`（默认 `<项目根>/logs/dev.log`，追加写 + 5MB 轮转 `.1`，dev/prod 均落盘子进程 stdout+stderr，启动写分隔行），`.gitignore` 忽略 `logs/`；② 前端快照 404 时顶部横幅提示「后端未提供工作区快照接口（404）：代码已更新但服务未重启，请重启 dev 栈」，不再只打 console.error | 用户要求「查看后端报错信息」时发现 stderr 经 launcher pipe 直达 pts，滚屏后无文件可查；根因是未重启而非代码缺陷，故同时补「日志可查」与「未重启可诊断」。后端 555 passed + 1 skipped（`test_launcher.py` 新增 log-file 两项）、前端 117 passed |

### 2026-11-19

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-11-19 | 需求 | 上线前终审·后端 12 项修复（逐项 RED→GREEN）：① 静态外壳放行（`_is_public_shell`：`/`、`/index.html`、`/assets/*`、favicon 免令牌，`/data` `/export` `/report` `/sessions` 仍强制）——修 prod 单端口 + 鉴权整页 401 白屏；② `POST /sessions/{sid}/workspace/{dsid}/activate` 落快照（此前切工作区重启即回落）；③ `chart_config` 每步下发 `charts` 白名单（`ToolSpec.charts`），`chart_choice` 校验 alpha∈[0.001,0.2]/layout∈{separate,shared}/correction∈{holm,bonferroni,none}/chart_type 越界降级为该工具首个可用图（此前 `float("abc")` 穿透）；④ `_release_task_slot`：后台任务按 `asyncio.current_task()` 身份释放槽位（被取消的旧任务不再清掉新任务登记与忙锁）；⑤ `delete_session` 一并清理 `_requests/_pending_chats/_revision_notes/_busy/_tasks/_interpret_tasks`（内存泄漏）；⑥ 恢复的审阅态可确认交付（句柄不在内存时按已恢复报告交付，同 restore_all 不走转移表）；⑦ `_jsonify` 归一 np.bool_/NaN/±Inf/NaT/pd.Timestamp，`table` 同样归一（否则 `websocket.send_json` 抛 TypeError、前端整帧丢弃卡在「执行中」）；⑧ `/export` 拒绝负数下标（曾静默导出末步）；⑨ `MEDSTA_MAX_ROWS` 非法值回退 20 万（不再 500）；⑩ 模板导出名校验；⑪ `_on_plot_later` 非法 step_index 不崩；⑫ `_answer` 忙判定先于「正在回答」进度帧 | 上线前终审（前后端全栈审计）：静态外壳白屏、切工作区不生效、图表白名单、interrupt 竞态、删除后内存常驻、恢复态不可交付、表格 NaN 破坏 WS 帧；后端 544 passed + 1 skipped、覆盖率 90%、ruff/mypy 清零 |
| 2026-11-19 | 需求 | 上线前终审·前端 10 项修复：① 工作区标签切换经 `POST .../activate` 同步后端 `active_dataset_id` 并回写会话绑定（此前只改本地显示 → 「看到新表、分析旧表」静默错分析）；② `data_profile` 增 `active` 语义位：仅首次绑定/显式激活改绑定，已绑定会话再上传只加标签（046 约定不变）；③ 多文件拖拽逐个弹窗（`pendingQueueRef` + Promise 让 `useFileDrop` 顺序等待）——此前单槽位会被后来的文件覆盖而静默丢文件；④ 单列类型编辑回调带 `datasetId`（此前按会话绑定数据集落库，改插补表会改到原表）；⑤ 导出 JSON/CSV/Excel、审阅卡「查看图表」、模板导出直链补 `?token=`（多用户模式此前必 401）；⑥ 出图配置等待期输入框只读（此前发消息被 SESSION_BUSY 拒绝且 error 帧清卡 → 无卡可确认的死角）；⑦ 交互卡（chart_config/type_review/plot_suggest/column_type_suggestions）按会话落地，切走再切回仍在（此前切回后卡消失、输入又只读 → 会话卡死）；⑧ WS close 4401/4403 停止无限退避重连并回登录卡（后端重启后令牌全失效）；⑨ 审阅卡显式提示「统计结果已生成但图表渲染失败：`chart_error`」；⑩ 能力抽屉 `role=dialog`/`aria-modal` + Esc 关闭，`plan` 事件清理过期交互卡，跨报告 React key 唯一（含 `result-card`） | 审计发现的前端功能异常（工作区/绑定一致性、多文件丢失、鉴权直链、交互死角）；前端 107 passed（新增 App.workspace 4 项）、E2E 2 passed、lint 仅 1 条既有 react-refresh 警告 |
| 2026-11-19 | 需求 | 批次 13 批量清理重复会话（用户实测痛点「138 个堆积会话逐个删太累」，RED→GREEN）：`POST /sessions/cleanup_duplicates`——按绑定数据集名分组、每组保留快照 mtime 最新者、其余经批次 12 的删除路径整目录清理；未绑定与执行中会话跳过（返回 deleted/kept/skipped）；归属隔离：`list_by_owner` 圈定候选 + 鉴权中间件为该集合级动作加白名单豁免（非单会话资源，无归属可查；令牌校验仍生效——曾因 /sessions/{x} 一律按 session_id 归属判定而 404）；`SessionStore.mtime`（快照 ns 级 mtime，排序不依赖创建顺序）；前端会话标签行新增「清理重复」按钮（confirm 确认 + 结果横幅 + 活跃会话被删自动切换 + lastSeq/消息缓存清理） | 批次 12 交付时用户提出；后端 534 passed、前端 101 passed |
| 2026-11-19 | 需求 | 批次 12 会话删除（用户实测痛点「会话选项卡堆积无法清理」，RED→GREEN）：新增 `DELETE /sessions/{sid}`（归属校验沿用中间件；async 路由 + `service.delete_session`——取消后台任务/工作流协程、弹出 plans/reports/句柄、`manager.delete` + `SessionStore.delete` rmtree 会话目录〔快照+数据+事件流+产物〕）；前端标签旁新增「×」删除按钮（`window.confirm` 确认防误删；删除活跃会话自动切换到剩余首个；清理本地 lastSeq/消息缓存）；`SessionTabs` onDelete 可选 prop 保持向后兼容；组件级 + REST + 多用户归属隔离测试 | 用户实测：旧流程每次上传强制新建会话导致选项卡堆积 138 个且无删除入口；后端 532 passed、前端 99 passed |
| 2026-11-19 | 需求 | 批次 11 生产加固（RED→GREEN 六项）：login 常数时间比较（compare_digest，未知用户空占位保耗时一致）+ 失败限速（同 IP 60s 窗口 5 次 → 429，成功清零）；`_extract_delta` 对 null delta 的 SSE chunk 显式回退（此前 AttributeError 不在捕获元组，部分兼容端必崩）；强制 log_normal 补正性门（NaN 静默传播威胁严格 JSON 契约）；`_on_type_confirm` 批量预检列存在（半更新防护，先行项不再落库）；chi_square/mcnemar params-only 与后段「两列来源」特例自洽（消除先拦矛盾）；ws 循环 RuntimeError 留警告日志（业务异常已在 handle 内转错误帧）；`evaluation-report.md` 补 046 基线补记与 §7 上线收尾评估、`design-notes.md` 补 §18（批次 1–11 架构决策） | 上线收尾评估前置：多用户暴力破解防护、兼容端 SSE 崩溃、交付数据完整性、半更新防护；后端 530 passed + 1 skipped、覆盖率 90%（实测） |
| 2026-11-19 | 需求 | 046 上传体验（spec 驱动，RED→GREEN）：① 行数上限——数据行数超过 `MEDSTA_MAX_ROWS`（默认 20 万，可调）→ 400 并清理已写文件（宽扁表 50MB 可达数百万行，快速拒绝优于长时间同步画像）；② 工作区/会话数据去向选择——已绑定数据的会话再上传时（chat「+」/工作区「+」/全局拖拽三入口统一）先弹 `UploadChoiceDialog`：加入当前工作区（同会话新增数据集标签，`handleUpload` 显式目标不再强制新建）/ 新建会话（旧行为）/ 取消；`handleUpload` 签名改 `target:{sessionId?,forceNew?}`，上传失败错误卡沿用 | TO_DO P1 两项：超大行数表画像耗时未治理 + 强制新建会话剥夺后端本就支持的「同会话多数据集」能力；spec/done/046-upload-experience.md（B1–B6）；后端 524 passed、前端 96 passed |
| 2026-11-19 | 需求 | 045 数据清洗层（spec 驱动，垂直切片 RED→GREEN）：新增 `stats/cleaning.py` 六工具——`dedupe`（整行/子集去重，keep=first/last，无重复不产数据集）、`filter_rows`（conditions 十操作符 AND，筛后 0 行显式拒绝）、`standardize`（z-score/minmax 列内变换）、`bin_column`（等频/等宽分箱，新增 {col}_bin 整数箱号 1..k）、`outlier_report`（IQR k 可调 / z-score 3σ，报告型）、`winsorize`（IQR/百分位截尾）；数据产出型遵循 028 impute 约定（cleaned_step_{i}.csv + `_next_frame` 037 链间管道 + service 注册 dataset_added imputed=false）；注册表新「数据清洗」类目、dedupe/filter_rows 入 _NO_TARGET_TOOLS、数值目标列 accepts=(continuous,)；MethodType 同步六名（test_method_contract）；METHOD_NOTES 补六条口径（test_textbook_conformance）；JSON 契约采样补六例；附录 A（28）/tools.md/product-guide 同步；前端 dataset_added 提示语按 imputed 标志区分 | TO_DO P1「数据清洗层」：上传脏数据需先去重/筛/变换再分析；spec/done/045-data-cleaning.md（行为 B1–B20、测试映射）；后端 523 passed + 1 skipped、前端 95 passed |
| 2026-11-19 | 需求 | 执行阶段 WS 收包拆分（批次 8）：`AnalysisWorkflow` 拆 create（同步建句柄）/start（阻塞至 TriggerFlow 首个暂停点），`run` 保留为兼容入口；`_execute_plan` 改为同步启动——登记句柄后由 `_execution_task` 后台驱动至审阅等待，计算期间 interrupt/chat 实时处理（此前 handler 阻塞至 async_start 返回，中断名存实亡）；执行句柄关闭移交被取消任务的后台路径（Agently `async_close` 的 `_drain_pending_tasks` 会等计算线程收尾，不得阻塞 WS 收包循环）；accept/revise 弹出句柄后取消后台任务 + 「启动即 accept」竞态返回 NO_ACTIVE_RUN；`run_chain` 增执行期 SESSION_BUSY 门控（防后台执行期覆盖 session.plan）；服务级测试 12 处补 wait_idle 对齐异步契约，TimeoutWorkflow/ExplodingWorkflow 替身改 create/start 形态 | 审查 P1「执行阶段 WS 收包阻塞」：技术验证 Agently 源码（async_start 经 _async_run_start 派发 START、auto_close=False 时阻塞至暂停点；async_close drain pending tasks）；`test_interrupt_during_compute_is_immediate` 守护（RED→GREEN） |
| 2026-11-19 | 需求 | 审查修复批六批次落地（每项 RED→GREEN）：批次 1 六项 P0——`_answer_task` finally 释放忙锁、`_on_chat` 执行/出图期门控（SESSION_BUSY）、`_on_resume` 执行期不降级（`AnalysisWorkflow.execution_done` 助手）、前端插补工作区显式选择优先（App.tsx 解析顺序 + 会话切换同步 effect）、vite 代理补 /auth /report /templates、配对检验按原始行序剔整对（methods.py，错位实例 statistic 2.0 vs 正确 1.6）；批次 2 状态守卫——`_execute_plan` 三异常路径统一 teardown、review accept/revise 清 `_workflows`、中断帧唯一化（`_generate_plan` CancelledError 只 raise）；批次 3 阻塞 IO——AI 类型建议与补绘 `to_thread`、上传/列类型/激活/报告导出路由 def 化线程池、解析失败清理孤儿文件、`EventLog` 改 O(1) 追加 + 阈值原子轮转（tmp+os.replace）；批次 4 统计口径——McNemar 单元格含义按列联表真实水平生成、中位生存期改 KM 阶梯定义（S(t)≤0.5 最小观测时间）、ORDINAL_HINT 文案对齐实现、parser utf-8 失败回退 gb18030、插补数据集用真实 CSV 路径经 `attach_data` 注册（快照恢复不再整会话失败）；批次 5 前端契约——终结事件按 ownerSid 落状态（isActive 只控渲染与全局卡）、首连 resume（恢复会话 last_seq=0 全量回放）、`createSession` 失败抛错、`CHART_OPTIONS` 拆 chartOptions.ts 补 survival_curve、直链 `?token=`（后端 auth_guard 双模式支持 + withToken 包装 /data /export /report）；批次 6 治理——ci.yml 补 ruff/mypy 与 ci.sh 互为镜像、ci.sh 前端改 test:coverage、附录 B 状态/事件一致性断言（B8/B9） | 全项目 Agently 审查报告的 P0/P1 清单；前端 95 passed（+7 新测试）、后端目标文件全绿 + ruff/mypy 清零 |
| 2026-11-19 | 结构 | 删除空壳模块 `backend/src/medsta/storage/`（`__init__.py` 无实现，架构图曾误指向）并修正 `manager.py` docstring 的持久化归属描述（session/persistence + events + LocalRecordStore）；孤儿草稿 `pipline.md` 归档至 `spec/archived/`（内容已由 spec 013–017 吸收）；前端 `CHART_OPTIONS` 常量拆分至 `chat/chartOptions.ts`（消除 react-refresh 警告）；`App.tsx` 事件处理 per-session 化（phase/messages 按 ownerSid 落地，全局交互卡保持 active-only） | 审查发现：storage 为幽灵包、pipline.md 系 spec 化前草稿、架构文档与代码漂移的结构性根因 |
| 2026-11-19 | 结构 | `docs/architecture.md` 三图对齐 032–044 现状：图 1 分层架构补鉴权（038/044）/SessionStore（032）/EventLog（035/036）/工具装配 Tab（033–037）/reporting 报告导出（040）/templates（034）节点，移除指向空壳 `storage/__init__.py` 的幽灵 D3 节点改指真实持久化模块；图 3 执行流程补 `run_chain` 装配链与 `resume`+`last_seq` 断线补发分支；新增「4. 所有权与不变量账本」（Agently Owner 划分 10 行）；附录 B 重写——事件表补 `chat_rejected`/`column_type_suggestions`/`type_confirmed`/`plot_suggest`/`interrupted`/`resumed`/`error`/`{type}_user` 回放帧，状态表修正为代码实际四态（删不存在的 `AWAITING_REVIEW`、补 `PLAN_CONFIRMED` 与转移关系） | 全项目 Agently 审查发现架构文档滞后 12 个 spec；B5 守护只数边数不校验节点真实性、附录 B 无一致性断言，漂移未被捕获 |
| 2026-11-19 | 结构 | `medsta/app.py` 模块级 app 改 PEP 562 惰性构建（`__getattr__` + globals memoize）：导入模块不再触发真实数据根的 restore_all/目录创建/网关构建副作用；uvicorn `medsta.app:app` 字符串目标首次取属性时构建（launcher 命令不变）；测试内 `create_app()` 调用点全部改传 tmp_path 数据根（`test_app`×3、`test_chart_flow` 内嵌 app），E2E 桩后端显式 `set_interpret_agent(None)` 防真实 .env 烧 token | 审查 P2（模块级实例副作用）+ P1 地雷的 E2E 面；`test_env_isolation.py` B2 守护惰性行为 |
| 2026-11-19 | 规范 | 统计口径变更——中位生存期由线性插值改为 KM 阶梯定义（教材 §14-2 / R 口径，`test_median_survival_uses_step_definition` 守护）、McNemar 交付表格 cell 含义按真实水平生成（不再假定「排序第二水平=阳性」）、ORDINAL_HINT 不再承诺未兑现的自动非参数；守护测试新增 B8（附录 B 状态表 == SessionStatus 枚举）与 B9（附录 B 事件表 ⊇ service/ws 实际下发事件）；CI 远端补 lint/type 两道门（`.github/workflows/ci.yml`），与 `scripts/ci.sh` 恢复互为镜像 | 审查结论：提示与实现不符、文档漂移无断言守护、远端 CI 弱于本地镜像（lint/类型不强制） |
| 2026-11-19 | 规范 | conftest 新增 autouse 夹具 `_no_real_gateway`：monkeypatch `medsta.config.build_gateway` 抛 RuntimeError（`_build_service` 为函数局部导入，调用期从源模块解析即被拦截）——开发机存在真实 `.env` 时测试内 app 工厂一律不构建真实智能体；`real_llm` marker（`MEDSTA_REAL_LLM=1` 冒烟）显式豁免；「测试不得依赖 `.env`」由约定变为机制 | 审查 P1 地雷：`test_export_chart_formats` 曾因 conftest 应用的真实 InterpretationAgent 在交付态 chat 打真模型而无限挂死；`test_env_isolation.py` B1 以显式 setenv 模拟 .env，在任意环境确定性守护 |
| 2026-11-19 | 规范 | 直链鉴权边界与审阅交付语义定稿：(a) 鉴权只保护业务数据，SPA 静态外壳匿名可取（`tests/test_auth.py::test_spa_shell_public_but_data_protected` + `test_multiuser.py::test_static_shell_reachable_without_token` 守护）；(b) 恢复期交付属「状态重建」，允许 `session.status = DELIVERED` 直接赋值，`SessionManager` 转移表保持 `discussing ⇏ delivered` 不放宽（`test_transition_rejects_invalid_jump` 不变）；(c) `chart_config.steps[].charts` 与 `data_profile.active` 成为前后端契约字段（`types.ts` 同步） | 旧行为「`/` 401」使 prod + 鉴权无任何入口可登录（B5 用例改写）；放宽转移表会削弱状态机守卫，故选恢复期特例 |
| 2026-11-19 | 环境 | 依赖补 `xlrd>=2.0`（`backend/pyproject.toml`）：pandas 的 .xls 引擎是 xlrd，openpyxl 只支持 .xlsx；缺包时 `.xls` 上传必然 ImportError。`load_table` 增加缺包可执行提示（「安装 xlrd 或另存为 .xlsx」），并补 `tests/fixtures/legacy.xls` 真解析用例 | 端到端核对「UI 宣称支持的 CSV/xlsx/xls」时发现 .xls 从未成功过（`import xlrd` MISSING）；后端 544 passed |

### 2026-11-16

| 日期 | 类型 | 内容 | 原因/依据 |
|---|---|---|---|
| 2026-11-18 | 需求 | 044 多用户化（课题组会话隔离）：env `MEDSTA_USERS`（用户:密码,...）启用；`POST /auth/login` 换令牌（secrets 内存表，重启失效需重登）；身份中间件扩展（038 之上）——注入 request.state.username 并按路径提取 sid 统一校验归属（/sessions|export|report|data/{sid}** 非 owner 一律 404 不泄露存在性），WS 归属校验 close 4403；Session.owner 随快照持久化/恢复；`GET /sessions` 当前用户会话列表（补「重启后前端不可见」缺口）；模板保持课题组共享；前端登录卡（401 触发）+ localStorage 令牌 + apiFetch 统一认证头 + WS ?token= + 会话列表恢复；B1 兼容硬证据——未配置 USERS 时既有测试零改动全绿 | 用户确认课题组共享部署；后端 485 passed（+4）、前端 88 passed（+2） |
| 2026-11-17 | 需求 | 043 输入守卫——模型只服务统计任务：两层拦截，第一层宿主预筛 `_looks_like_chitchat`（纯问候/致谢/告别/单字符，零 token 直接拒绝，先于模型与数据检查）；第二层模型同请求自检——`AnalysisPlan`/`AnswerReply` 增 `off_topic`/`off_topic_reason` 契约字段（不增加额外调用），模型判定无关时宿主拦截：讨论态发 `chat_rejected`（前端 notice 气泡引导描述统计需求、phase 重置 idle），答疑态替换为范围提示 | 用户需求「避免闲聊无关问题烧 token」；Owner 合规——守门是成本控制非语义决策，语义判断仍归模型；后端 481 passed（+9）、前端 86 passed（+1） |
| 2026-11-17 | 需求 | 042 拖拽导入数据文件：`hooks/useFileDrop`（window 级 dragover/dragleave/drop；文件类拖拽才响应、扩展名白名单 csv/xlsx/xls、多文件顺序上传避免并发竞态）；拖入悬停显示全屏遮罩（虚线卡片「松开鼠标导入数据文件」），drop 后复用现有上传管道（自动建会话/绑定工作区） | 用户需求「增加拖拽导入文件功能」；hook 可单测（jsdom Event+defineProperty 模拟 dataTransfer）；前端 85 passed（+5）；多用户化顺延为 043 |
| 2026-11-17 | 需求 | 041 模型辅助列类型确认（AI 确认数值类型）：`agents/type_advisor.py` ColumnTypeAdvisor（结构化契约 name/suggested_type/confidence/reason，宿主校验非法建议丢弃进 skipped）；证据白名单（列名/规则推断类型/前 5 个唯一样本值/缺失数/基数/统计，不传全量数据）；WS `suggest_column_types` → `column_type_suggestions`；前端 ProfileTable「AI 确认类型」按钮 + 建议徽标（类型+置信度+理由）+ 单列采纳/全部采纳（复用单列与批量 PATCH，用户敲定）；未配模型返回 MODEL_UNAVAILABLE 配置提示 | 用户需求「设计一个工具，能让模型帮我确认数值类型」；Owner 合规：模型只做语义建议、宿主校验、用户保留敲定权；后端 472 passed、前端 80 passed |
| 2026-11-17 | 需求 | 用户实测五项缺陷修复：①聊天内「前往工作区查看与导出」由纯文本改为可点击按钮（切 Tab+聚焦），执行产出区条件改 reports（无图有表也显示，导出报告按钮可见）；②顶部 Tab 增聚焦模式——点击将该栏最大化（再点恢复三栏并排），桌面三栏不再「点了没反应」；③装配器 column 参数全部改下拉选择上传表格的列（group_by/group_column 等，杜绝手填出错）；④卡方/McNemar 的分组柱状图改按列联表计数绘制（此前误用数值均值路径画出空图）；⑤切会话/新会话时重置绘图确认、补图、类型审阅交互卡（此前全局单例跨会话残留） | 用户实测报告五项；⑤根因是交互态全局单例，per-session 改造经测试验证有回归风险后改为「切会话重置」等价方案；后端 468 passed、前端 78 passed、构建通过、浏览器冒烟确认 |
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

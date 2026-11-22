# MedSta TO_DO

> 与 `docs/timeline.md` 同步维护：每次变更必须同时更新本文件（状态/下一步）与时间线（历史记录）。
> 时间线记「已发生」，本文件记「接下来」；评估依据与验收口径见 `docs/evaluation-report.md`。

## 进行中

| 任务 | 状态 | 说明 |
|---|---|---|
| — | 暂无 | 审查整改、功能批次 1–13 与上线前终审（前后端 22 项）全部落地（见已完成）；剩余 P2 见下方清单 |

## 下一步（按「用户可见价值 × 依赖关系 × 成本」排序）

> P0 方法学、032–046（持久化/工作链/模板/重连回放/管道/鉴权/工程质量/报告导出/输入守卫/多用户/上传体验/清洗）全部落地。
> 基线（2026-11-20 047 工作流编排后）：后端 pytest 全绿（601 passed + 1 skipped 真模型冒烟，覆盖率 90%）+ ruff/mypy 清零、前端 136 passed、E2E 2 passed、CI 五道门（lint/类型/测试/覆盖率/E2E）远端与本地镜像一致。

### 候选方向（需用户输入优先级）

- 多用户化二期（在线用户列表、令牌过期与登出）——044 已落地鉴权与隔离
- 工作链市场（模板共享/评分，依赖多用户）
- 严格 mypy（disallow_untyped_defs）与前端路由分包
- E2E 扩展（鉴权开关场景、模板导入导出路径的浏览器级覆盖）

### P1 其余精选（按痛点）

- [x] **测试环境隔离 .env（P1 地雷）**：conftest autouse 夹具强制 `build_gateway` 抛错（`real_llm` 冒烟豁免）+ 模块级 app 惰性化 + E2E 桩 `set_interpret_agent(None)`；`test_env_isolation.py` 两项守护（2026-11-19 批次 7 落地）
- [x] 执行阶段 WS 收包拆分：`create/start` 拆分 + 后台执行任务 + 句柄关闭移交被取消任务；计算期间 interrupt 实时生效（2026-11-19 批次 8 落地，Agently 源码验证 async_start/async_close 语义）
- [x] 数据清洗层：去重、异常值识别/截尾、标准化、分箱、筛选子集（2026-11-19 批次 9 / spec 045 落地，六工具 + 注册表 + 链间管道 + dataset_added 注册）
- [x] 上传行数限额：`MEDSTA_MAX_ROWS`（默认 20 万，可调）→ 400 并清理已写文件（2026-11-19 批次 10 / spec 046）
- [x] 工作区/会话绑定一致性：已绑定会话再上传统一弹「数据去向」选择——加入当前工作区 / 新建会话 / 取消（2026-11-19 批次 10 / spec 046）
- [ ] 多重性完整化：Hochberg、gatekeeping、图形法；亚组交互检验

### P2 工程质量（按审查报告剩余项）

- [x] login 加固：常数时间比较（`secrets.compare_digest`）与速率限制（同 IP 60s 窗口 5 次失败 → 429，成功清零）（2026-11-19 批次 11）
- [ ] `RE_EXECUTE` 修正回边决策：生产链路从未触发（仅测试使用）——接线或移除（当前产品语义为 revise→cancel→再讨论，倾向移除死边）
- [x] **047 重跑正确性两处（2026-11-21）**：`_input_frame` 重放上游 `impute`/清洗的 `_next_frame` 后再跑目标节点（重跑与补图共用）；`_rerun_from` 每个节点结果调用 `_mark_node`，成功清掉过期失败原因
- [x] `ws.py` RuntimeError 到达留警告日志（业务异常已在 handle 内转错误帧）；`config.py` SSE null delta 显式回退（2026-11-19 批次 11）
- [x] 计划期条件必填校验：dunnett→control_group（含对照组必须出现在分组列）、cox→covariates、logrank→group_col（2026-11-21，不再拖到运行期 ValueError）
- [x] 统计边界簇：回归类别自变量点名拒绝、`render_combined` 不足两张图直接拒绝、饼图改用 tab20 不再只给 6 色（2026-11-21）
- [x] 前端 P2 簇：重连回放与本地 echo 按文案+seq 合并为一条气泡；补绘图按钮连点只发一帧（2026-11-21）。**剩余**：装配器 conditions 参数表单打磨
- [x] 恢复的审阅态可确认交付（终审：句柄不在内存时按已恢复报告交付，`test_restored_review_can_be_delivered` 守护）
- [ ] evaluation-report / design-notes 基线刷新（现冻结在 029/030，README 承诺失效；§19 已补终审决策）
- [ ] 前端路由级分包、i18n；OpenAPI/WS 契约自动生成 + `hypothesis` 属性测试
- [x] 后端 `ruff` + `mypy` 常态清零（批次 3 起纳入 CI 双门）；`print`→`logging`：服务代码已完成（余 10 处在 launcher.py 属 CLI 终端输出，保留）
- [x] CI：pytest + vitest + playwright + 覆盖率门槛 83%（spec 021；批次 6 补齐 ruff/mypy 远端双门）
- [x] 终审一致性（2026-11-19）：工作区激活前后端同源、静态外壳鉴权边界、`.xls` 依赖、任务槽位竞态、删除会话旁路状态、WS 令牌失效不再无限重连——详见 timeline 当日 4 条与 `docs/design-notes.md` §19
- [x] 残留清理（2026-11-20）：`scripts/clean_sessions.py` 一条命令清空残留会话（在线走 API 保持内存与磁盘一致），E2E 桩后端启动自清 `/tmp/medsta-e2e-*`

## 已完成

| 任务 | 完成日期 | 产出 |
|---|---|---|
| 手册复审对齐 047/048 | 2026-11-20 | `docs/handbook.md` 重写心跳与四章、新增「会话上下文」「推荐流程」「定点修正」「节点级交付」等章节；契约补 `step_result`/`retry_step`/`amend_step`、`plan.flow`、`GET /templates/builtin`、`POST .../chain/match`；前端五维分桶与 `PlanFlowView`/`StepDeliveryCard`；审查发现重跑不重放上游数据产物、未回写上下文两处缺口（已进 P2） |
| 方案 rationale 自动补全 | 2026-11-20 | 输出契约显式声明 `rationale`/`depends_on`；缺依据时自动补一轮（宿主只合并 rationale）并在补完仍缺时保留硬门；方案卡显示「依据未提供」。后端 585 passed + 1 skipped、前端 129 passed |
| 多轮图不清除 + 修正后无反应 | 2026-11-20 | 图表只展示最新一轮（历史轮次折叠汇总），统计表按轮次保留；带意见的 revise 自动接续讨论（`back_to_discussion` + 自动重出方案），前端提交即锁定审阅卡；`histogram` + `params.group_by` 支持按类别分面出图。后端 601 passed + 1 skipped、前端 136 passed |
| 参数驱动目标的工具不再被误拒 | 2026-11-20 | `ToolSpec.target_param` 贯通（校验/目录/规范化重建保留）；`_NO_TARGET_TOOLS` 补 missing_report/aggregate_table；slots 与真实参数名对齐；模板非法 fixed 修正；新增「每条内置模板匹配后逐步骤硬校验」守护。后端 598 passed + 1 skipped、前端 133 passed |
| 工作链推荐模板 + AI 一键匹配（048） | 2026-11-20 | 5 条按 skills 预设的内置流程；宿主筛候选 + 模型语义选择 + 合法性复核（候选外丢弃）+ 失败回退规则；逐步 `validate_step` 移除不可执行步骤；前端推荐卡一键载入、来源标签、编辑就地替换。后端 595 passed + 1 skipped、前端 133 passed |
| 统计工作流编排（047） | 2026-11-20 | 流程图方案（`plan_flow` + `PlanFlowView`，节点=工具/边=依赖）；逐节点交付（`step_result`，失败不阻断）；断点续接（`retry_step` 重跑该节点及下游、`amend_step` 模型定点重写）；`SessionContextStore` 按 owner→session 分层；内置 12 条统计 skills（SAMPL/决策树/误用）注入 prompt。前端审计五项收口（isActive 实时化、类型契约、回放空气泡、定时器泄漏、记录旁路化）。后端 581 passed + 1 skipped、前端 129 passed、E2E 2 passed |
| 目标列 vs 分组列的误用防线 | 2026-11-20 | 校验 hint 给出可执行修法（类别列 → `params.group_column`）；`tool_catalog` 下发 `group_param`，装配器按 `accepts` 实时提示并「一键设为分组列」；错误卡结构化展示 issues；讨论 prompt 明确类别列不得进 `target_columns`。后端 558 passed + 1 skipped、前端 121 passed |
| 后端日志落盘与「未重启」诊断 | 2026-11-20 | launcher `--log-file`（默认 `logs/dev.log`，追加 + 5MB 轮转）；前端快照 404 顶部横幅提示重启 dev 栈。根因：dev 的 uvicorn 无 `--reload`，09:56 的旧进程没有新路由 `GET /sessions/{sid}/workspace`，新前端持续 404 |
| 类型确认体验 + 会话同步 + 模块卡折叠 | 2026-11-20 | 「AI 确认类型」加载态（spinner + 说明 + 90s 兜底 + 结果/错误复位）；`PATCH .../columns` 带 `source` 并广播 `type_confirmed`（`SessionService.attach_sender/broadcast` → seq 落事件流 + 在线推送，无连接也能回放），会话区按来源生成可核对文案，采纳后按列消费建议；单列修改改走批量端点（此前不广播）；工作区四块（画像/统计表/结果数据/执行产出）可折叠（默认展开、`aria-expanded`）。后端 553 passed + 1 skipped（`test_type_sync.py` 5 项）、前端 116 passed（`App.typeSync.test.tsx` 5 项）、E2E 2 passed |
| 教学版产品与实现手册 | 2026-11-20 | `docs/handbook.md`（13 章）：三条铁律、一次会话 20 步心跳、后端启动链与 `SessionService` 账本、Agent 侧 Owner 判据与证据工程、TriggerFlow 句柄时序、注册表校验顺序、前端四维分桶状态与事件映射、契约/错误码速查、四层测试与文档守护、8 个动手实验、排错表、代码地图；README 与 product-guide 补入口并修正过期计数锚点 |
| 残留会话清理机制 | 2026-11-20 | `scripts/clean_sessions.py`（在线走 API 删内存+磁盘、离线删目录、`--purge-records` 停服后清执行记录、顺带清 `/tmp/medsta-e2e-*`）；E2E 桩后端启动自清旧临时根；**conftest autouse 把无参 `create_app()` 的默认数据根重定向到 tmp**（堵住 9 处用例写真实 `backend/data` 的缺口，`test_default_create_app_writes_into_tmp` 守护）；README 补命令；本次清掉 214 个历史会话目录与 11 个 E2E 临时根，清理后 API/磁盘/tmp 均为 0 |
| 刷新后工作区与会话区同源 | 2026-11-20 | 新增 `GET /sessions/{sid}/workspace` 快照（画像 + 激活项 + 当前报告，归属 404）；前端进入会话拉快照并与回放幂等合并（`report_id` 去重）；`WorkspaceTab.sessionId` 归属 + 标签/计数按会话过滤 + 无绑定时清空选择；刷新自动回到上次会话（localStorage）；报告先到的占位迁移；`resumed` 按服务端 stage 校正 phase（回放的历史 progress 不再把界面永久卡在「执行中」）。后端 547 passed + 1 skipped、前端 111 passed（`App.hydrate.test.tsx` 4 项）、E2E 补「刷新后左右同源」断言 |
| 上线前终审（前后端 22 项） | 2026-11-19 | 后端 12 项：静态外壳鉴权放行（prod+鉴权不再白屏）、工作区激活落盘、`chart_config` 每步 charts 白名单 + chart_choice 参数校验、任务槽位身份释放（interrupt 竞态）、删除会话清旁路状态、恢复审阅态可交付、`_jsonify` 归一 np.bool_/NaN/Inf/NaT、导出负数下标拒绝、MEDSTA_MAX_ROWS 兜底、模板导出名校验、plot_later 下标兜底、答疑忙判定顺序；前端 10 项：工作区切换同步后端+回写绑定（消「看新表算旧表」）、多文件拖拽队列、单列类型带 datasetId、直链补 token、出图配置期输入只读、交互卡按会话保留、WS 4401/4403 停止重连回登录卡、chart_error 提示、能力抽屉 a11y+Esc、plan 清过期卡与 key 唯一；依赖补 `xlrd>=2.0`（.xls 真解析 + fixture）；E2E 2 处定位/文案修正。后端 544 passed + 1 skipped（覆盖率 90%）、前端 107 passed、E2E 2 passed、ruff/mypy 清零 |
| 批量清理重复会话（批次 13） | 2026-11-19 | `POST /sessions/cleanup_duplicates`（按绑定文件名分组保留最新〔快照 mtime〕，未绑定/执行中跳过，deleted/kept/skipped 返回）；鉴权中间件集合级动作白名单（曾按 session_id 归属误判 404）；`SessionStore.mtime`；前端「清理重复」按钮（confirm + 结果横幅 + 活跃切换）；后端 534 passed + 1 skipped、前端 101 passed |
| 会话删除（批次 12） | 2026-11-19 | `DELETE /sessions/{sid}`（归属校验 + async + 工作流协程取消）；`SessionStore.delete` rmtree 会话目录（快照/数据/事件流/产物）；前端标签「×」删除按钮（confirm 防误删、活跃切换、本地状态清理）；REST/组件/多用户归属三组测试；后端 532 passed + 1 skipped、前端 99 passed |
| 生产加固 + 上线收尾评估（批次 11） | 2026-11-19 | login 常数时间比较 + 60s 窗限速（429）；SSE null delta 回退；强制 log_normal 正性门；type_confirm 半更新防护；chi_square params-only 豁免；ws RuntimeError 留痕；`evaluation-report.md` 046 基线补记 + §7 生产就绪度评估；`design-notes.md` §18 决策补记；后端 530 passed + 1 skipped、覆盖率 90% |
| 上传体验：行数限额 + 数据去向选择（批次 10，spec 046） | 2026-11-19 | 上传行数上限 `MEDSTA_MAX_ROWS`（默认 20 万，400 并清理文件）；已绑定会话三入口（chat「+」/工作区「+」/拖拽）统一弹 `UploadChoiceDialog`（加入当前工作区 / 新建会话 / 取消）；`handleUpload` target 化（显式目标不再强制新建）；后端 524 passed + 1 skipped、前端 96 passed |
| 数据清洗层（批次 9，spec 045） | 2026-11-19 | `stats/cleaning.py` 六工具（dedupe/filter_rows/standardize/bin_column/outlier_report/winsorize）；注册表「数据清洗」类目 + MethodType/JSON 采样/METHOD_NOTES/附录 A（28）/tools.md/product-guide 全链同步；cleaned_step_{i}.csv 产物 + `_next_frame` 链间管道 + service 注册（dataset_added imputed=false）；21 项新测试，后端 523 passed + 1 skipped、前端 95 passed |
| 执行阶段 WS 收包拆分（批次 8，P1） | 2026-11-19 | `AnalysisWorkflow.create/start` 拆分（run 保留兼容）；`_execution_task` 后台驱动执行至审阅；计算期间 interrupt/chat 实时处理（此前 handler 阻塞、中断名存实亡）；句柄关闭移交被取消任务后台路径（Agenty `async_close` drain 计算线程不阻塞 WS）；accept/revise 取消后台任务 + 启动即 accept 竞态 NO_ACTIVE_RUN；run_chain 执行期门控；新增 `test_interrupt_during_compute_is_immediate` 守护；服务级测试 12 处对齐异步契约 |
| 测试环境隔离 .env（批次 7，P1 地雷 + 同域 P2） | 2026-11-19 | conftest autouse 夹具 `_no_real_gateway`（补丁 `medsta.config.build_gateway`，real_llm 冒烟豁免）；`medsta/app.py` 模块级 app 惰性构建（PEP 562，uvicorn 目标不变）；test_app/test_chart_flow 内嵌 `create_app()` 全部改传 tmp_path 数据根；E2E 桩 `set_interpret_agent(None)`；新增 `test_env_isolation.py` 两项守护（B1 任意环境确定性 RED→GREEN、B2 惰性行为） |
| 全项目 Agently 审查整改（六批次，RED→GREEN 逐项） | 2026-11-19 | 批次 1 P0×6（busy 泄漏/执行期 chat 门控/resume 降级/插补工作区/vite 代理/配对错位）；批次 2 状态守卫族（异常 teardown、accept+revise 清句柄、中断帧唯一）；批次 3 阻塞 IO×5 + EventLog 追加写与原子轮转；批次 4 统计口径×5（McNemar 语义/中位生存期阶梯/ORDINAL_HINT/GBK 回退/插补真实路径）；批次 5 前端契约×5（per-session 事件落地/首连回放/createSession 抛错/图表枚举/`?token=` 直链）；批次 6 治理（ci.yml 对齐 ci.sh、B8/B9 文档断言、storage 空壳删除、pipline.md 归档、chartOptions 拆分）；后端 ruff/mypy 清零、前端 95 passed、文档守护 11 项全绿 |
| 全项目 Agently 审查 + 架构图对齐 032–044 | 2026-11-19 | 审查报告（后端编排 / 统计数据 / 前端 / 文档 CI 四线问题清单与分级整改建议）；`docs/architecture.md` 三图重绘 + 所有权与不变量账本 + 附录 B 事件/状态表修正 |
| 034–044 十一个 spec（模板/重连回放/链间管道/单令牌鉴权/工程质量/报告导出/AI 列类型/拖拽导入/输入守卫/多用户化/实测五修） | 2026-11-16~18 | 逐条详见 `docs/timeline.md`；基线后端 485 passed、前端 88 passed |
| 原子统计工作链（033，产品定位调整） | 2026-11-16 | WS `run_chain` 手动装配通道（validate_plan 硬校验/跳过出图确认/零模型可执行/交付态可装配）；前端「工具装配」Tab（分类选工具+动态参数表单+工作链编辑+方案导入）；JSON 输出硬门（22 工具逐个采样 allow_nan=False + 覆盖性守护）；`format=json` 表格导出与图 JPG/PDF/TIF 导出；`docs/tools.md` 登记+一致性守护；前端 JSON/多格式下载；后端 423 passed、前端 57 passed |
| 会话持久化（032）+ 三处顺手修 | 2026-11-16 | `SessionStore` JSON+原子写、6 个落盘点、启动恢复（列类型重放）、resume 还原审阅/交付态、executing 降级；落盘先于送达；历史报告 report_id 寻址导出（前后端）；文本列改数值 to_numeric 兜底（S5）；图表失败与统计隔离（E1）；后端 393 passed、前端 53 passed |
| P0/P1 审查修复批 | 2026-10-24 | 统计正确性七处（Breslow w²、RMST 组间 tau、McNemar 分类豁免、AUC 平均秩、配对 bootstrap 差值重抽样、Fisher 路径 Cramér's V、卡方星号顺序）；SPA 路径穿越（resolve 前缀校验）、导出公式注入转义、上传 50MB 限额；状态机转移表 + SESSION_BUSY 忙锁 + WS 错误帧兜底 + 执行 to_thread 化 + 审阅超时语义；matplotlib>=3.9；前端 estimand 透传；后端 382 passed、前端 52 passed |
| 架构图与说明文档（031） | 2026-10-23 | `docs/architecture.md` 三张 Mermaid 图（分层架构 / 统计策略选择 / 执行流程）+ 22 工具附录与事件状态对照；`docs/product-guide.md` 产品说明；README 瘦身为入口；`test_docs_consistency.py` 六条一致性断言；后端 364 passed、前端 51 passed、覆盖率 89.81% |
| 阶段评估与 P0 修复（030） | 2026-10-23 | `evaluation-report.md` 重写为 029 基线（019→029 六维度对比、G0–G7 门禁、六类缺陷复盘、剩余缺口，综合 7.9/10）；`competing_risk`/`multiplicity_control` 描述改为「已实现/未实现」并加 3 条契约测试；022–029 成果按 4 个自包含提交入库；`.gitignore` 忽略 31MB 教材 PDF；后端 356 passed、前端 51 passed、覆盖率 89.81% |
| Estimand / SAP 结构化（029） | 2026-10-23 | `EstimandSpec` 五要素（人群/变量/处理/伴发事件+五策略/汇总指标）；`sap_status_of` 宿主判定 `estimand_declared`/`exploratory`；`plan` 事件下发；方案卡折叠展示与缺失项提示；caveat 按状态二选一；前后端文案红线扫描；后端 353 passed、前端 51 passed、覆盖率 89.81% |
| 缺失数据路径（028） | 2026-10-23 | `missing_report` 升级为缺失模式诊断（univariate/monotonic/arbitrary + 分组差异提示 + 阈值警告 + 机制声明）；新增 `impute`（MICE 20 次取均值 + 插补间方差、median/mean/LOCF 仅敏感性、delta 扫描）；插补数据集经 `dataset_added` 写入工作区且不切换 active；scikit-learn 列为必需依赖；后端 339 passed、前端 48 passed、覆盖率 89.74% |
| 生存分析族（027） | 2026-10-23 | KM（教材表 14-2 逐行复现）+ Greenwood SE + 中位生存期插值 + 风险人数表；log-rank 多组二次型、Breslow；Cox（HR/CI/LR/Wald/Score/schoenfeld）+ RMST；`survival_curve` 图表；`ChartType` 一致性测试；后端 316 passed、前端 44 passed、覆盖率 89.64% |
| 时间线重构与下一步计划（026） | 2026-10-23 | `docs/timeline.md` 改为倒序决策时间线（49 条，六类标签，同日按类型排序），roadmap 重排 |
| 事后比较与设计类方法（025） | 2026-10-23 | Tukey/Dunnett/LSD-t/Schéffé、析因、重复测量、样本量；scipy 下限 1.14 |
| 第六至十章口径（024） | 2026-10-23 | 单样本检验、随机区组、McNemar、SNK-q、四格表三档、χ² 分割、Kendall τ |
| 教材口径校准（023） | 2026-10-23 | `descriptive_stats`、`reference_range`、相关/回归增强、`METHOD_NOTES` |
| 结果解释与答疑分流（022） | 2026-10-23 | 证据白名单 + 因果硬门 + 非阻塞 `interpretation` + 交付态答疑 |
| CI 流水线（021） | 2026-10-21 | GitHub Actions 三作业；后端覆盖率 88.19%，门槛 83% |
| 正确性护栏（020） | 2026-10-21 | 整数测量变量识别、Logistic 分离检测、`PROTOCOL_UNSUPPORTED` |
| 全链路测试体系（019） | 2026-10-21 | 四层金字塔、测试隔离、修复 10 类缺陷、`evaluation-report.md` |
| 会话×工作区绑定（018） | 2026-10-19 | 一会话一表、消息隔离、思考折叠修复 |
| 类型系统/前置确认/工作区语义（015–017） | 2026-10-19 | 四类变量类型、type_review、类型驱动映射、工作区交付 |
| 多工作区/槽位化/出图确认（012–014） | 2026-10-19 | 多工作区 Tab、task/slots/applicability、chart_config、导出 |
| 选项与能力披露（011） | 2026-10-18 | `AnalysisPlan.options`、`/capabilities`、能力抽屉 |
| 实时交互（010） | 2026-10-18 | 错误码体系、流式输出、中断/继续、步骤进度 |
| 统计工具库（009） | 2026-10-18 | `stats/{registry,methods,plotting}.py`、执行器注册表派发 |
| 一键启动器（008） | 2026-10-17 | `python main.py` dev/prod 双模式 |
| 初始骨架（001–007） | 2026-10-17 | 后端骨架、解析与画像、讨论智能体、pipeline、工作流、会话 API、前端 SPA |

## 已知限制

- 统计描述未实现频数表加权法（教材 2-2/2-5，仅在无原始数据时使用）。
- 方差分析支持完全随机、随机区组、两因素析因（含一阶交互）与单因素重复测量；三因素及以上交互、裂区设计未实现。
- 重复测量未做球形性校正（Mauchly/Greenhouse-Geisser），混合设计（组间+组内）与缺失数据处理未实现。
- 两两比较支持 SNK-q、Tukey、Dunnett、LSD-t、Schéffé、Holm、Bonferroni；Dunnett 需显式指定对照组组名。
- 样本量工具支持六种设计；非劣效/等效设计、整群与区组随机化的样本量未实现。
- 生存分析支持右删失的 KM / log-rank / Breslow / Cox / RMST；竞争风险（Fine–Gray）、时依协变量、分层 Cox、参数生存模型与左截断未实现。
- 缺失数据支持 MICE 单数据集插补与 delta 扫描；完整多重插补（Rubin 合并）、MMRM、tipping point、MNAR 选择模型与纵向缺失未实现。
- 估计目标（Estimand）仅展示与状态标注：SAP 摘要导出、事前注册、盲态与样本量论证未实现；五要素文本不做与数据列的语义校验。
- 多重性目前覆盖 SNK/Tukey/Dunnett/LSD/Schéffé/Holm/Bonferroni；Hochberg、gatekeeping、图形法与期中 α 消耗未实现。
- 聊天消息流已可完整回放（036：用户动作帧落盘+回放）；事件日志轮转为保留尾部一半的简单策略。
- 上传已有 50MB 大小限额（超限 413）和行数限额 `MEDSTA_MAX_ROWS`（默认 20 万，超限 400 并删除已写文件）。上传路由是同步 `def`，由 FastAPI 放进线程池，不占事件循环。
- 结果解读为单轮生成：不支持重新生成、不支持跨多次交付的多轮答疑记忆；解读文字质量依赖真实模型（CI 仅验证契约与守卫）。
- Logistic 分离目前「拒绝输出」，未提供 Firth 惩罚回归；共线性仅通过系数/收敛间接暴露。
- 分支保护（要求 CI 必过才能合并）需在 GitHub 仓库设置中手动开启；CI 不接入真实模型，`real_llm` 保持默认 skip。
- 架构图为 Mermaid 源码（可渲染、可 diff），未导出 PNG/SVG；贴到 PPT 或对外文档需自行截图。

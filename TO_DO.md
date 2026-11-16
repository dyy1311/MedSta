# MedSta TO_DO

> 与 `docs/timeline.md` 同步维护：每次变更必须同时更新本文件（状态/下一步）与时间线（历史记录）。
> 时间线记「已发生」，本文件记「接下来」；评估依据与验收口径见 `docs/evaluation-report.md`。

## 进行中

| 任务 | 状态 | 说明 |
|---|---|---|
| — | 暂无 | 037/038/039 三候选全部完成并归档；后续候选见下方 |

## 下一步（按「用户可见价值 × 依赖关系 × 成本」排序）

> P0 方法学、032–039（持久化/工作链/模板/重连回放/管道/鉴权/工程质量）全部落地。
> 基线：后端 457 passed + ruff/mypy 清零、前端 77 passed、CI 三道门（lint/类型/测试）。

### 候选方向（需用户输入优先级）

- 多用户化（会话级鉴权与隔离、在线用户列表）——多人共享部署的下一道门
- 工作链市场（模板共享/评分，依赖多用户）
- 严格 mypy（disallow_untyped_defs）与前端路由分包
- E2E 扩展（鉴权开关场景、模板导入导出路径的浏览器级覆盖）

**为什么排第一**：032 已提供快照数据源，断线重连与回放是其自然延伸；
前端目前断线后消息静默丢弃、界面卡死（审查 H2）。

- 范围：WS 指数退避重连 + 连接状态指示、事件序号与补发（不重复投递）、历史会话回放还原聊天流
- 验收：断线 10s 内自动重连且不重复投递；回放能还原交付态与消息流
- 风险：事件序号触及全部事件类型（后端出站 + 前端处理）；聊天消息流需随快照落盘（032 未含）

### P1 其余精选（按痛点）

- [ ] **会话持久化 + WS 断线重连 + 历史回放**：当前会话仅存内存，重启即丢（内部使用最痛）
- [ ] 数据清洗层：去重、异常值识别/截尾、标准化、分箱、筛选子集
- [ ] 上传限额（大小/行数）+ 异步解析（`to_thread`），避免阻塞事件循环
- [ ] 工作区/会话绑定一致性：上传新表时让用户选择「加入当前工作区 / 新建会话」
- [ ] 多重性完整化：Hochberg、gatekeeping、图形法；亚组交互检验

### P2 工程质量

- [ ] `print` → `logging`（16 处），补 request/session id 与 `/metrics`
- [ ] 前端路由级分包、错误边界、i18n；移除未使用依赖
- [ ] 后端 `ruff` + `mypy`；数值告警显式处理
- [ ] OpenAPI/WS 契约自动生成 + `hypothesis` 属性测试
- [x] CI：pytest + vitest + playwright + 覆盖率门槛 83%（spec 021）

## 已完成

| 任务 | 完成日期 | 产出 |
|---|---|---|
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
- 上传已有 50MB 大小限额（超限 413）；行数限额与异步解析（`to_thread`）未实现，解析仍在主事件循环同步执行。
- 结果解读为单轮生成：不支持重新生成、不支持跨多次交付的多轮答疑记忆；解读文字质量依赖真实模型（CI 仅验证契约与守卫）。
- Logistic 分离目前「拒绝输出」，未提供 Firth 惩罚回归；共线性仅通过系数/收敛间接暴露。
- 分支保护（要求 CI 必过才能合并）需在 GitHub 仓库设置中手动开启；CI 不接入真实模型，`real_llm` 保持默认 skip。
- 架构图为 Mermaid 源码（可渲染、可 diff），未导出 PNG/SVG；贴到 PPT 或对外文档需自行截图。

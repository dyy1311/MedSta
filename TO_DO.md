# MedSta TO_DO

> 与 `docs/timeline.md` 同步维护：每次变更必须同时更新本文件（状态/下一步）与时间线（历史记录）。
> 评估依据与验收口径见 `docs/evaluation-report.md`。

## 进行中

| 任务 | 状态 | 说明 |
|---|---|---|
| — | 暂无 | spec 019（全链路测试体系）已完成并迁入 `spec/done/`；下一步按下方 P0 启动新 spec |

## 下一步（roadmap，按评估优先级）

### P0 方法学与正确性

- [ ] 生存分析族：Cox / KM / RMST / Fine–Gray（`survival_analysis` ToolSpec，PH 假设与删失测试）
- [ ] 缺失数据路径：MICE（≥20 次）、MMRM、delta/tipping；LOCF/均值填补仅限敏感性并强制提示
- [ ] Estimand（E9(R1) 五要素）与 SAP 结构化；缺失时方案标记「探索性」
- [x] Logistic 完全/准完全分离检测（spec 020：未收敛 / max|β|≥15 / OR 非有限即拒绝；Firth 惩罚仍待实现）
- [x] 整数型连续变量（年龄等）误判 ordinal 的识别与一键修正（spec 020：列名词元匹配 + 跨度规则 + 类型确认卡批量操作）
- [ ] 结果解释：模型生成受控文字结论（证据引用、禁止过度因果）

### P1 产品完整性

- [ ] 数据清洗层：去重、异常值、标准化、分箱、筛选子集
- [ ] 多重性完整化：Hochberg / Dunnett / gatekeeping / 图形法；亚组交互检验
- [ ] 会话持久化（重启不丢）、WebSocket 断线重连、历史会话回放
- [ ] 上传限额（大小/行数）+ 异步解析（`to_thread`）
- [ ] 工作区与会话绑定一致性：上传新表时让用户选择「加入当前工作区 / 新建会话」

### P2 工程质量

- [ ] `print` → `logging`（16 处），补 request/session id 与 `/metrics`
- [ ] 前端路由级分包、错误边界、i18n；移除未使用依赖
- [ ] 后端 `ruff` + `mypy`；数值告警显式处理
- [ ] CI：pytest + vitest + playwright（缓存浏览器）+ 覆盖率门槛 + OpenAPI/WS 契约测试 + hypothesis 属性测试

## 已完成

| 任务 | 完成日期 | 产出 |
|---|---|---|
| 正确性护栏（020） | 2026-10-21 | 整数测量变量识别（年龄/血压→连续）、Logistic 分离检测（拒绝溢出 OR）、`PROTOCOL_UNSUPPORTED` 错误码、类型确认卡「数值列全部设为连续」；后端 200 collected、前端 35 passed |
| 全链路测试体系（019） | 2026-10-21 | 后端 195 collected（1 项真模型 skip）、前端 34 passed（覆盖率 88.61%）、E2E 2 passed；新增 129 项用例；修复 10 类缺陷（工作区报告不可见、交付态按钮、上传错误静默、WS 类型校验、group_compare >2 组等）；`docs/evaluation-report.md` |
| 项目初始化（001–007） | 2026-10-17 | 后端骨架、数据解析、讨论智能体、pipeline、会话 API、前端 SPA、真实模型接入修复 |
| 一键启动器（008） | 2026-10-17 | `python main.py` dev/prod 双模式 |
| 统计工具库（009） | 2026-10-18 | 60 项测试全绿；`stats/{registry,methods,plotting}.py`；executor 注册表派发 |
| 实时交互（010） | 2026-10-18 | 12 错误码、流式输出、中断/继续、步骤进度 |
| 选项与能力披露（011） | 2026-10-18 | `AnalysisPlan.options`、`/capabilities`、能力抽屉与选项按钮 |
| 多工作区 / 槽位化 / 出图确认（012–014） | 2026-10-19 | 多工作区 Tab、task/slots/applicability、策略链、chart_config/choice、表格交付与导出 |
| 类型系统 / 前置确认 / 工作区语义（015–017） | 2026-10-19 | 四类变量类型、type_review 门控、类型驱动映射、工作区交付 |
| 会话×工作区绑定（018） | 2026-10-19 | 一会话一表、会话 Tab、消息隔离、思考折叠修复 |

## 已知限制

- 生存分析（Cox、Fine–Gray、RMST、Win Ratio）未实现，能力披露中标注「规划中」。
- 缺失数据只能报告，不能插补；无敏感性分析（delta/tipping）。
- 多重性目前仅 Holm/Bonferroni；Hochberg、Dunnett、gatekeeping、图形法与期中 α 消耗未实现。
- WebSocket 断线重连、历史会话回放未实现；会话仅存内存，重启丢失。
- 无上传大小/行数限额；解析在主事件循环同步执行。
- 无结果解释（自然语言结论）生成；交付为表格、图表与策略链。
- Logistic 分离目前「拒绝输出」，未提供 Firth 惩罚回归；共线性仅通过系数/收敛间接暴露。

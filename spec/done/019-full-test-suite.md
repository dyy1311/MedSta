# 019 - 全链路测试体系与项目评估

> 状态：done
> 创建：2026-10-21 ｜ 敲定：2026-10-21 ｜ 完成：2026-10-21
>
> 落地结果：后端 195 collected（194 passed + 1 真模型 skip）、前端 34 passed（语句覆盖率 88.61%）、
> 浏览器 E2E 2 passed；`npm run build` / `npm run lint` 通过；发现并修复 10 类缺陷（详见 `docs/evaluation-report.md`）。
> 真模型冒烟用例已实现并注册 `real_llm` marker，按设计默认 skip，本轮未消耗额度执行。

## 背景与目标

项目已具备上传→画像→讨论→确认→执行→交付全链路，但测试集中在后端 21 个文件约 102 项，
**前端零测试基础设施**，且上传边界、多会话隔离、导出异常、WS 全事件链、绘图矩阵等关键行为
没有回归保护。本 spec 的目标是：

1. 建立四层测试金字塔（单元/方法层 → 服务编排层 → REST/WS 契约层 → 前端层）；
2. 用两个方法学 HTML（《医学统计处理流程图》G0–G7 八道门禁 + 四块决策板、《顶刊统计策略图谱》）
   作为**评估基线**，逐条对照当前能力，产出差距矩阵；
3. 测试暴露的缺陷按 TDD 修复至全绿，不留下已知红灯。

## 范围

- 做：
  - 后端：上传契约（成功/拒绝/脏表/多表）、多会话隔离、画像质检与缺失报告、12 类统计方法与
    策略链、显著性校正、11 类图表与拼图/字体回退、计划级校验、执行报告与失败隔离、
    CSV/XLSX 导出与异常路径、WS 全事件链与中断/继续/错误码、真模型冒烟（env 门控）
  - 前端：`client.ts` 契约、`App` 双栏/窄屏布局、会话 Tab、工作区面板、上传→方案→出图→审阅交互
  - 浏览器层：Playwright 全流程（桩模型后端 + Vite dev）
  - 文档：`docs/evaluation-report.md`（评分、G0–G7/决策板差距矩阵、P0/P1/P2 建议）
- 不做：
  - 不新增统计方法（生存分析/MICE/Dunnett 仍为 planned，只进评估建议）
  - 不做完整 RCT/临床试验流程自动化（门禁属方法学评估，不塞进单元测试）
  - 不引入快照测试、不引入第二套断言库、不改动既有公共契约
    （`AnalysisPlan` / WS 消息 / `ExecutionReport` / `types.ts`）

## 行为列表（TDD 循环队列）

- [x] B1: 上传 CSV/XLSX 返回 `data_profile`，含 dataset_id、行列数与逐列画像
- [x] B2: 上传拒绝不支持的扩展名（400）、未知会话（404）；错误可被前端读取
- [x] B3: 脏表（空行/纯空格/`NA`/BOM/中文表头）可解析且画像行数、缺失数正确；空文件返回错误而非 500
- [x] B4: 同会话上传多表生成互不覆盖的 dataset_id，首表保持激活
- [x] B5: 两个会话的消息、方案、执行报告与工作区互不污染；记录按 session_id 分桶
- [x] B6: `POST /workspace/{id}/activate` 切换激活表；`PATCH columns` 修正类型后 `type_confirmed=True`，非法列/类型返回 404/400
- [x] B7: 画像推断四类变量（continuous/ordinal/categorical/index），连续列输出七列口径，缺失报告支持 group_by
- [x] B8: describe/missing_report/normality_test/levene_test/aggregate_table 输出结构与数值口径正确
- [x] B9: group_compare/anova 策略链（正态性→Levene→失衡→最优/次优），非正态降级非参数、方差不齐用 Welch
- [x] B10: 2×2 小期望频数自动降级 Fisher；大样本走卡方并输出 Cramér's V
- [x] B11: correlation/regression/logistic_regression/timeseries_forecast 输出 r/p、系数 CI、OR/AUC、预测长度
- [x] B12: 计划级硬校验（工具/列/必填参数/枚举/类型不匹配/rationale）拒绝执行并给出结构化 issue
- [x] B13: ExecutionReport 逐步记录；单步失败隔离（failed + error.code），其余步骤仍交付；`_layout=shared` 合并 artifact
- [x] B14: 11 类图表均产出有效 PNG；中文标题无缺字警告；pairwise 显著性标注；组合图生成 charts_combined.png
- [x] B15: 导出 CSV（UTF-8-SIG 可还原中文）与 XLSX（openpyxl 可读）；无报告/无表格 404、非法格式 400、标题含斜杠净化
- [x] B16: WS 全事件链：`type_review → type_confirmed → plan → chart_config → progress → review_request → delivered`
- [x] B17: 中断/继续/未知消息/未知会话/非法选项均返回带 code/hint 的 error 或对应事件，不崩溃
- [x] B18: 前端 `client.ts` 各请求的 URL/method/错误分支正确；WS 发送仅在 OPEN 态、坏 JSON 不抛；artifactUrl 契约
- [x] B19: 前端布局与交互：双栏、窄屏 Tab 切换、会话 Tab 条、工作区空态/画像表/表格交付/图表卡、方案选项、出图配置、审阅接受/修正、错误卡
- [x] B20: 浏览器 E2E 全流程（上传→讨论→确认→执行→交付→导出）通过；真实模型冒烟默认 skip，`MEDSTA_REAL_LLM=1` 才运行

## 验收标准

- [硬门] B1–B17 全部 pytest 通过，且可在无 `.env`、无网络的模拟模型下跑完
- [硬门] B18–B19 vitest + Testing Library 通过（jsdom，仅 mock fetch/WebSocket 网络边界）
- [硬门] B20 Playwright Chromium 用例通过；若浏览器下载受限，降级为 B18/B19 全绿并在报告注明原因
- [硬门] `npm run build` 与 `npm run lint` 不回归
- [硬门] 测试不污染 `backend/data`：数据根与记录目录全部落在 `tmp_path`
- [软标] 测试命名读起来像行为规格（用户可观察），不耦合私有实现
- [软标] 评估报告能直接用于立项评审：差距有出处（G0–G7 / 决策板 A–D）、建议有优先级与验收口径

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1–B4 | `POST /sessions`、`POST /sessions/{id}/data` | `tests/test_upload_contract.py` |
| B5–B6 | `POST /workspace/{id}/activate`、`PATCH .../columns`、`SessionManager` | `tests/test_multisession.py` |
| B7 | `profile_dataframe`、`apply_column_type`、`missing_report` | `tests/test_profile_quality.py` |
| B8–B11 | `stats.registry.execute_step` / `validate_step` | `tests/test_stats_methods.py`、`tests/test_significance.py` |
| B12 | `validate_plan`、`PipelineExecutor.execute` | `tests/test_plan_guard.py` |
| B13 | `PipelineExecutor.execute`、`ExecutionReport` | `tests/test_execution_report.py` |
| B14 | `stats.plotting.render_chart` / `render_combined` | `tests/test_plotting.py` |
| B15 | `GET /export/{sid}/{index}` | `tests/test_export_delivery.py` |
| B16–B17 | WS `/ws/{sid}`、`SessionService.handle` | `tests/test_ws_contract.py` |
| B18 | `frontend/src/api/client.ts` | `src/api/client.test.ts` |
| B19 | `App.tsx` 与 `chat/`、`workspace/` 组件 | `src/App.layout.test.tsx`、`src/App.flow.test.tsx`、`src/workspace/WorkspacePanel.test.tsx` |
| B20 | 真实后端 + 前端 | `frontend/e2e/full-flow.spec.ts`、`tests/test_real_llm_smoke.py` |

模型输出契约不变：`AnalysisPlan{message, steps[], options[]}`，`PlanStep{step_id?, title, method, target_columns, chart_type, params, rationale}`；
WS 事件契约与 `frontend/src/types.ts` 保持一致，测试只断言已声明字段。

## 依赖与影响

- 依赖 001–018 既有契约；不修改统计数值口径与 WS 协议。
- 为测试隔离做三处最小改动：
  1. `api/routes_data.py`：数据根从模块常量改为请求期解析（`request.app.state.data_root` 优先），
     避免测试写入真实 `backend/data/sessions`；生产行为不变。
  2. `app.create_app()`：注入 `app.state.data_root`，并与 `_build_service()` 使用同一根目录。
  3. `session/manager.py`：新增 `clear()` 供测试清场（仅测试调用）。
- 前端 `vite.config.ts`：proxy target 支持 `MEDSTA_API` 环境变量，Playwright 与本地 dev 可并存。

## 备注

- 既有 `backend/e2e_smoke.py` 保留为人工冒烟脚本，不重复维护为 pytest 用例；
  自动化 E2E 走 `frontend/e2e/full-flow.spec.ts` + `backend/tests/e2e_app.py`（桩模型，不消耗额度）。
- 数据清洗能力现状：仅 `missing_report` + 列类型修正，无插补/异常值/去重。
  测试覆盖现有质检语义，缺口写入评估报告 P0/P1 建议。

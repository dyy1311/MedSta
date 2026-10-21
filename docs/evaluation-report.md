# MedSta 项目评估与全链路测试报告

> 日期：2026-10-21 ｜ 对应 spec：`spec/done/019-full-test-suite.md`
> 评估基线：《医学统计处理流程图 · 可复用工作流 v1.0》（八道门禁 G0–G7、四块决策板 A–D）
> 与《医学统计前沿方法论 · 顶刊统计策略图谱》。

## 0. 结论摘要

- 本次新增 **129 项自动化用例**（后端 +93、前端 +34、浏览器 E2E +2），
  项目累计 **231 项**（后端 195、前端 34、E2E 2），全部通过；前端语句覆盖率 **88.61%**。
- 测试暴露并修复 **10 类实现缺陷**，其中 2 项直接破坏交付闭环：
  工作区永远收不到执行报告（`activeChatRef` 从未赋值，表格/图表/导出入口全部不可见）、
  已交付后审阅卡仍显示「确认交付」（状态与 UI 不一致）。
- 项目工程底座扎实（Owner 划分清晰、注册表单一真相源、契约测试友好），
  但**方法学完整度是最大短板**：按顶刊门禁衡量，G1（估计量）、G2（设计定档）、G5（稳健性）基本缺失，
  生存分析、缺失数据处理、多重性控制、样本量与 MCID 均未落地。
- CI 已接入（spec 021）：推送 main/PR 自动跑后端、前端与 E2E 三作业，后端覆盖率门槛 83%；
  分支保护仍需在 GitHub 后台手动开启。
- 综合评分 **7.4 / 10**：可作为「探索性数据分析 + 规范图表交付」工具投入内部使用；
  在补齐 P0 项之前，不应宣称可支撑确证性临床研究或投稿级分析。

| 维度 | 评分 | 依据 |
|---|---|---|
| 架构与职责划分 | 8.5 | 模型只做语义决策；校验/算术/副作用归宿主；`stats/registry.py` 单一真相源 |
| 契约与可测试性 | 8.5 | `AnalysisPlan` / WS 事件 / `ExecutionReport` 三层契约稳定；模型仅在传输边界可替换 |
| 统计实现正确性（已覆盖方法） | 7.5 | 12 类方法数值可复现；策略链与校正正确；但完美分离、>2 组等边界有风险 |
| 方法学完整度（对照 G0–G7） | 4.0 | 生存/竞争风险/纵向/缺失/敏感性/估计量全缺 |
| 前端体验与可维护性 | 7.5 | 双栏工作台、类型确认、出图确认、策略链展示完整；无错误边界/重连/历史回放 |
| 工程质量（测试/CI/可观测） | 7.5 | 四层测试 + GitHub Actions 三作业 + 后端 83% 覆盖率门槛（实测 88.19%）；仍无结构化日志、ruff/mypy |
| **综合** | **7.4** | 内部探索性分析可用，确证性分析需补齐 P0 |

## 1. 测试资产与运行方式

### 1.1 四层测试金字塔

| 层 | 位置 | 数量 | 隔离手段 | 关注点 |
|---|---|---|---|---|
| 方法层 | `backend/tests/test_stats_methods.py`、`test_significance.py`、`test_plotting.py`、`test_profile_quality.py` | 47 | `tmp_path` | 数值口径、策略链、PNG 产物、类型推断 |
| 编排/契约层 | `test_upload_contract.py`、`test_multisession.py`、`test_plan_guard.py`、`test_execution_report.py`、`test_export_delivery.py`、`test_ws_contract.py` | 45 | `app.state.data_root` + `SessionManager.clear()` | REST/WS 契约、状态机、错误码、交付导出 |
| 真模型冒烟 | `test_real_llm_smoke.py` | 1（默认 skip） | `MEDSTA_REAL_LLM=1` + `.env` | 真实链路最小验证 |
| 既有回归 | 001–018 的 21 个文件 | 102 | 同上（已接入共享夹具） | 既有能力不回退 |
| 前端组件层 | `frontend/src/**/*.test.tsx` | 34 | 仅 mock `fetch`/`WebSocket` | 布局、交互、事件映射、client 契约 |
| 浏览器层 | `frontend/e2e/full-flow.spec.ts` | 2 | 桩模型后端 + Vite dev | 真实浏览器全流程、响应式、导出 |

### 1.2 运行命令

```bash
# 后端全量（默认不触发真实模型）
cd backend && pytest

# 真实模型冒烟（显式开启，消耗额度）
cd backend && MEDSTA_REAL_LLM=1 pytest tests/test_real_llm_smoke.py -q

# 前端组件/布局/交互
cd frontend && npm test
cd frontend && npm run test:coverage

# 浏览器 E2E（自动拉起 8021 桩后端 + 5174 Vite）
cd frontend && npm run test:e2e
```

**实测结果（2026-10-21）**：后端 `194 passed, 1 skipped`；前端 `34 passed`；E2E `2 passed`；
`npm run build`、`npm run lint` 均通过。Playwright 优先方案执行成功（Chromium 已缓存，未降级）。

### 1.3 覆盖矩阵（用户诉求 → 落点）

| 诉求 | 覆盖内容 | 测试文件 |
|---|---|---|
| 上传 | CSV/XLSX、扩展名拒绝、未知会话、空文件、BOM/中文表头/脏数据、同会话多表 | `test_upload_contract.py` |
| 分会话 | 双会话方案/事件/记录隔离、工作区激活、列类型 PATCH、报告按会话分桶 | `test_multisession.py`、`test_export_delivery.py`、`App.layout.test.tsx` |
| 数据清洗（现有质检） | 四槽位类型、七列口径、缺失报告（分组）、类型修正重算、索引列排除 | `test_profile_quality.py` |
| 统计 | 12 类方法数值、策略链降级（非正态/方差不齐）、Fisher 降级、Holm/Bonferroni、计划级校验 | `test_stats_methods.py`、`test_significance.py`、`test_plan_guard.py` |
| 绘图 | 11 类 PNG 产物、拼图、显著性标注、字体回退、默认图表映射 | `test_plotting.py` |
| 交付 | 报告结构、失败隔离、artifact 文件名契约、CSV(BOM)/XLSX、404/400、文件名净化 | `test_execution_report.py`、`test_export_delivery.py` |
| 用户交互 | WS 全事件链、流式增量、中断/继续、类型确认错误码、未知消息/会话、选项/修正回退 | `test_ws_contract.py`、`App.flow.test.tsx` |
| 前端布局 | 双栏、Tab 切换、会话 Tab 条、工作区空态/画像/表格/图表、能力抽屉 | `App.layout.test.tsx`、`WorkspacePanel.test.tsx` |
| 前后端交互 | `client.ts` 请求/错误/WS 契约、Vite 代理可参数化、浏览器全流程 + 导出 | `client.test.ts`、`full-flow.spec.ts` |

## 2. 测试发现并修复的缺陷

| # | 缺陷 | 影响 | 修复 | 回归用例 |
|---|---|---|---|---|
| 1 | `routes_data.DATA_ROOT` 为导入期常量 | 测试直接写真实 `backend/data/sessions`，用例互相污染 | 数据根改为请求期解析；`create_app(data_root=...)` 注入 `app.state.data_root` | `test_upload_contract.py` 全量 |
| 2 | 空 CSV 解析异常冒泡 | 上传空文件返回 500 | 捕获解析异常 → 400 + 可读 detail | `test_upload_empty_file_returns_400_not_500` |
| 3 | CSV 用 `utf-8` 读取 | Excel 导出文件的 BOM 污染首列名（`\ufeff姓名`） | 改 `utf-8-sig` | `test_upload_dirty_csv_counts_missing_and_bom` |
| 4 | WS `type_confirm` 不校验类型 | 可写入 `banana` 类型，直达画像 | 先整体校验再落库 | `test_type_confirm_validates_column_and_type` |
| 5 | 未知会话 WS 断言崩溃 | 刷新/重连页面连接失效会话时连接断开 | `handle()` 前置检查 → `NO_ACTIVE_RUN` | `test_unknown_session_returns_error_instead_of_crashing` |
| 6 | `CHART_TYPES` 缺 `pie` | `/capabilities` 与实际可渲染图表不一致（前端下拉多出饼图但目录不披露） | 注册表补齐 `pie` | `test_chart_catalog_covers_all_rendered_types` |
| 7 | `activeChatRef` 从未赋值 | **执行报告永远进不了工作区** → 表格交付、图表、导出入口全部不可见 | 用会话列表 ref 按 `ownerSid` 查绑定表 | `执行结果进入工作区…`（RTL） |
| 8 | `delivered` 不更新审阅消息 | 已交付仍显示「确认交付」按钮 | 交付事件标记最后一条 review 消息 | `发送讨论消息 → … → 审阅交付`（RTL） |
| 9 | 上传失败只写 console | 用户点击上传无任何反馈 | 统一错误卡（`UPLOAD_FAILED`） | `上传失败时在会话流展示错误`（RTL）、E2E 第二例 |
| 10 | `group_compare` 遇 3 组静默只用前两组 | 第三组被无声丢弃，结论可能错误 | 计划期拦截并提示改用 `anova` | `test_group_compare_rejects_third_group_instead_of_silently_ignoring` |

附带修复：能力抽屉关闭按钮补 `aria-label`；清理 5 处 ESLint 死代码（`ChatPanel`/`ReviewCard`/`WorkspacePanel`）。

## 3. 方法学差距（对照八道门禁）

图例：✅ 已实现 ｜ 🟡 部分实现 ｜ ❌ 未实现

| 门禁 | 当前能力 | 判定 | 缺口 |
|---|---|---|---|
| **G0 问题分层** | 工具目录有 `task`（描述/关联/预测）；提示词要求先定任务类型 | 🟡 | 无 PICO/因果/决策结构化；无「探索性」标记与升级路径 |
| **G1 估计量（E9(R1)）** | 仅有方法选择与参数 | ❌ | 五要素（人群/变量/伴发事件/汇总/群体）全缺；无伴发事件策略 |
| **G2 设计定档** | 模型可在 `message` 里写设计说明 | ❌ | 无 RCT/非劣效/等效/TARGET/集群/平台/适应性设计的结构化校验 |
| **G3 样本量/数据契约** | 画像、类型确认、工具 `min_rows` 校验 | 🟡 | 无样本量/功效计算；无 SAP 冻结、分层因素锁定、缺失机制预判 |
| **G4 主分析** | t/ANOVA/卡方/相关/OLS/Logistic/趋势；协变量可通过 `regression` 近似 ANCOVA | 🟡 | 无生存/竞争风险/纵向/复合终点；无「唯一主分析」约束；无 ANCOVA 专用槽位 |
| **G5 稳健性与敏感性** | Holm/Bonferroni 校正；单步失败隔离 | ❌ | 无敏感性矩阵、MICE/MMRM、delta/tipping、E-value、未测混杂量化 |
| **G6 推断与不确定性** | 效应量（Cohen's d、η²/ε²、OR、R²）+ 95%CI；星号 | 🟡 | 无 MCID、无贝叶斯后验/决策阈值；星号阈值与用户 α 可分离（见 §4） |
| **G7 报告与复现** | 表格/图表/CSV/XLSX 导出；策略链可追溯 | 🟡 | 无复现包（代码/中间数据/SAP/偏离记录）、无随机种子、无 CONSORT/STROBE/TRIPOD+AI 清单 |

### 3.1 四块决策板对照

| 决策板 | 结论 | 说明 |
|---|---|---|
| **A 终点类型 → 主分析** | 1/6 覆盖 | 连续型 ✅；二分类 🟡（仅 Logistic OR/AUC，无 RR/RD/改良 Poisson/CMH）；时间-事件 ❌；竞争风险 ❌；复合/层级 ❌；纵向/重复测量 ❌ |
| **B 伴发事件 → 估计量策略** | 0/5 覆盖 | treatment policy / hypothetical / while-on-treatment / composite / principal stratum 全缺 |
| **C 缺失数据 → 处理路径** | 1/5 覆盖 | 仅缺失报告；MAR 的 MICE/MMRM、MNAR 的 delta/tipping、死亡作为伴发事件均缺。红线（LOCF/均值填补不得作主分析）目前靠「不做插补」间接规避，但无提示与守卫 |
| **D 多重性与期中** | 2/6 覆盖 | Holm/Bonferroni ✅；Hochberg/Dunnett/gatekeeping/图形法 ❌；期中 α 消耗/DMC ❌；亚组交互检验 ❌ |

## 4. 未修复问题与改进建议

### P0（正确性 / 方法学风险，建议下一迭代）

1. **生存分析族**（Cox、KM、RMST、Fine–Gray）：对应 G4/决策板 A 的最大空白。
   验收：新增 `survival_analysis` ToolSpec（时间列/事件列/协变量槽位），PH 假设检验，KM 曲线 + 风险人数表，测试覆盖删失。
2. **缺失数据路径**（MICE ≥20 次、MMRM、delta 调整/tipping point）：对应决策板 C。
   验收：`missing_report` 后给出机制→路径建议；LOCF/均值填补只能进敏感性并强制提示。
3. **Estimand / SAP 结构化**（G1/G3）：新增 `EstimandSpec` 五要素与设计矩阵；缺失时方案强制标记「探索性」。
4. **Logistic 完美分离与共线性**：现有测试已复现 `ConvergenceWarning` 与 `exp` 溢出（`methods.py:537`），
   极端 CI 仍会作为结果下发。验收：检测 separation → 可读错误或 Firth 惩罚；测试覆盖。
   *进展（spec 020，2026-10-21）：已实现未收敛 / max|β|≥15 / OR 非有限三重检测并拒绝输出；Firth 仍缺。*
5. **整数型连续变量误判**：`age=[25,31,42]` 推断为 `ordinal`（见 `test_upload_contract.py` 注释），
   导致参数检验被默认降级、功效损失。建议按列名/取值范围/小数位辅助识别，并提供「全部设为连续」一键操作。
   *进展（spec 020）：已实现列名词元/中文子串匹配 + 跨度规则 + 类型确认卡批量操作。*
6. **结果解读缺失**：交付只有表格/图/策略链，没有模型生成的自然语言结论。
   这与产品定位「交付图表与解释建议」不符，建议优先补（受控模板 + 证据引用 + 禁止过度因果表述）。

### P1（产品完整性）

- **数据清洗层**：去重、异常值识别/截尾、标准化、分箱、类型转换、筛选子集。当前仅有质检与类型修正，
  与用户「上传→清洗→分析」的心智模型有落差。
- **多重性完整化**：Hochberg、Dunnett、层级 gatekeeping、图形法；亚组交互检验（禁止挑亚组讲故事）。
- **前后端一致性**：UI 上传新表会自动新建会话，与后端「单会话多工作区」能力不一致；建议显式让用户选择
  「加入当前工作区 / 新建会话」。
- **会话持久化与恢复**：会话仅存内存单例，重启即丢；无 WS 断线重连、无历史回放。
- **性能与安全**：上传无大小/行数上限，同步解析阻塞事件循环；建议 `to_thread` + 限额 + 超时。
- **错误码语义**：未知消息类型返回 `INVALID_PLAN`，建议独立 `PROTOCOL_UNSUPPORTED`。

### P2（体验 / 工程）

- 可观测性：16 处 `print` 调试日志替换为 `logging`，补 request/session id；增加 `/metrics`。
- 前端：路由级代码分割、错误边界、i18n；未使用依赖 `recharts`、`react-icons`、`tailwind-merge` 可移除。
- 后端质量门：引入 `ruff` + `mypy`，对 `methods.py` 的数值溢出/收敛告警做显式处理。
- 测试体系：CI 编排（pytest + vitest + playwright 缓存）、后端 `pytest-cov` 门槛、
  OpenAPI/WS schema 自动契约测试、`hypothesis` 属性测试（如 CI 覆盖率、p 值边界）、Playwright 视觉回归。

## 5. 说明与边界

- 本报告的方法学判定以两份 HTML 的「门禁/决策板」为 checklist，不代表对具体临床研究方案的法律/合规结论。
- 「数据清洗」在现有代码中仅指质检与类型修正；插补/异常值/去重等能力不存在，相关测试未虚构。
- 真模型冒烟用例默认 skip，避免 CI 依赖外部 API 与消耗额度；开启方式见 §1.2。
- 后端未引入覆盖率工具，故未报告后端覆盖率；前端覆盖率来自 `npm run test:coverage`。

## 附录 A：本次新增/修改文件

新增：

```
spec/done/019-full-test-suite.md
backend/tests/{conftest.py,helpers.py,e2e_app.py,test_upload_contract.py,test_multisession.py,
  test_profile_quality.py,test_stats_methods.py,test_significance.py,test_plotting.py,
  test_plan_guard.py,test_execution_report.py,test_export_delivery.py,test_ws_contract.py,
  test_real_llm_smoke.py}
frontend/{vitest.config.ts,playwright.config.ts}
frontend/src/test/{setup.ts,mocks.ts}
frontend/src/{api/client.test.ts,App.layout.test.tsx,App.flow.test.tsx,workspace/WorkspacePanel.test.tsx}
frontend/e2e/{full-flow.spec.ts,fixtures/cohort.csv}
docs/evaluation-report.md
```

修改（生产代码限定最小必要）：

```
backend/src/medsta/api/routes_data.py      数据根请求期解析 + 解析失败 400
backend/src/medsta/app.py                  create_app(data_root) 注入 state
backend/src/medsta/session/manager.py      clear() 测试接缝
backend/src/medsta/session/service.py      未知会话守卫 + 类型确认校验
backend/src/medsta/stats/registry.py       补 pie；group_compare >2 组拦截
backend/src/medsta/data/parser.py          utf-8-sig
frontend/src/App.tsx                       工作区报告路由、交付标记、上传错误可见
frontend/src/chat/{ErrorCard,CapabilityDrawer,ChatPanel,ReviewCard}.tsx  错误码/无障碍/死代码
frontend/src/workspace/WorkspacePanel.tsx  死代码
frontend/vite.config.ts                    代理支持 MEDSTA_API
frontend/{package.json,tsconfig.app.json,tsconfig.node.json,.gitignore}
```

## 附录 B：关键回归命令

```bash
cd backend && pytest                              # 195 collected（1 skipped）
cd frontend && npm test                           # 34 passed
cd frontend && npm run test:coverage              # 语句 88.61%
cd frontend && npm run test:e2e                   # 2 passed（Chromium）
cd frontend && npm run build && npm run lint
```

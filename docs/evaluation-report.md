# MedSta 项目评估与全链路测试报告（029 基线）

> 日期：2026-10-23 ｜ 对应 spec：030（评估与 P0 修复）
> 上一基线：2026-10-21（对应 spec 019，综合 **7.4 / 10**）
> 评估基线：《医学统计处理流程图 · 可复用工作流 v1.0》八道门禁 G0–G7、四块决策板 A–D
> 与《医学统计前沿方法论 · 顶刊统计策略图谱》。旧版全文见 git 历史。

## 0. 结论摘要

- 项目从「12 类统计方法」扩展到 **22 类**，补齐生存分析、缺失数据、估计目标三块方法学空白；
  教材第二、三、六至十一、十四、十五章的口径已逐条落地，并用教材例题作为数值基准。
- 测试资产：后端 **356 passed + 1 skip**（51 个测试文件）、前端 **51 passed**（10 个文件）、浏览器 E2E **2 passed**；
  后端覆盖率 **89.81%**（门槛 83%）。
- 这三轮（023–029）修掉 **6 类真实缺陷**，其中 2 项会静默产出错误结论
  （均值差 CI 固定用 1.96、大样本 Shapiro 过度敏感把正态判成偏态）。
- 综合评分 **7.9 / 10**（019 基线 7.4）：方法学完整度从 4.0 提到 7.0 是主因；
  工程质量因「八个 spec 长期未提交」被扣分，该问题已在本 spec 修复。
- **仍不应宣称可支撑确证性临床研究**：Estimand 只做声明与展示，竞争风险、完整多重插补、MMRM 未实现。

## 1. 阶段交付

### 1.1 spec 波段（26 个已归档）

| 波段 | spec | 内容 |
|---|---|---|
| 底座 | 001–019 | 骨架、画像、讨论智能体、pipeline、WS 契约、注册表、实时控制、多工作区、类型确认、交付闭环、全链路测试 |
| 质量 | 020–021 | 正确性护栏（完美分离、CI 方向、`correction` 死参数）、CI 三作业流水线 |
| 产品 | 022 | 结果解读（证据白名单 + 因果硬门 + 句数截断）、交付后答疑分流 |
| 方法学 | 023–025 | 教材第二/三/十一章 → 第六至十章 → 事后比较、析因/重复测量、样本量 |
| 方法学 | 027–029 | 生存分析（KM/Cox/RMST）、缺失数据（MICE）、Estimand/SAP |

### 1.2 工具矩阵（22 类）

| 类别 | 工具 |
|---|---|
| 描述 | `describe` `descriptive_stats` `reference_range` `missing_report` `impute` |
| 前提与汇总 | `normality_test` `levene_test` `aggregate_table` |
| 设计 | `sample_size` |
| 比较 | `group_compare` `one_sample_test` `anova` `randomized_block_anova` `factorial_anova` `repeated_measures_anova` |
| 分类资料 | `chi_square` `mcnemar_test` |
| 关联与预测 | `correlation` `regression` `logistic_regression` `timeseries_forecast` |
| 时间-事件 | `survival_analysis` |

配套：13 类图表（含 `survival_curve`）；`method_note` 覆盖全部工具（教材章节与公式、适用条件、解读禁忌）。

### 1.3 工程指标

| 指标 | 数值 |
|---|---|
| 后端用例 | 356 passed + 1 skip（`real_llm` 默认跳过） |
| 后端覆盖率 | 89.81%（`stats/survival.py` 90%、`stats/descriptive.py` 94%） |
| 前端用例 | 51 passed |
| 浏览器 E2E | 2 passed |
| 核心代码 | stats + agents + session 约 6489 行 |
| 运行时依赖 | 新增 1 个：`scikit-learn>=1.3`（028） |

## 2. 评分对比（019 基线 → 029 基线）

| 维度 | 019 | 029 | 变化依据 |
|---|---|---|---|
| 架构与职责划分 | 8.5 | **8.5** | 新增 5 个模块沿用同一 owner 划分，无「模型算数」或「模型判定」的例外 |
| 契约与可测试性 | 8.5 | **8.5** | 新增 `MethodType`、`ChartType` 与注册表一致性守护；WS 事件向后兼容 |
| 统计实现正确性 | 7.5 | **8.5** | 教材例题逐个复现（表 14-2 十五行、例 3-3、例 11-2、例 2-6）；修正 3 处口径错误 |
| 方法学完整度 | 4.0 | **7.0** | 生存/缺失/Estimand 从 0 到有；竞争风险、完整 MI、MMRM、分层 Cox 仍缺 |
| 前端体验 | 7.5 | **7.5** | 内嵌解读、答疑卡、插补数据集标签页；仍无断线重连与历史回放 |
| 工程质量 | 7.5 | **7.0** | 用例数增长 54%，但 022–029 长期未提交、无结构化日志、无 ruff/mypy |
| **综合** | **7.4** | **7.9** | 方法学跃升为主因；工程分被版本管理问题抵消 |

## 3. 方法学门禁（G0–G7）

| 门禁 | 状态 | 现状 |
|---|---|---|
| G0 研究问题类型 | ✅ | `_TASK_META` 五类任务；方案卡片显式标注 |
| G1 估计量 | 🟡 | 029 提供五要素声明与状态标注；**不是事前 SAP，不能当作确证性依据** |
| G2 设计定档 | 🟡 | 工具目录有适用条件与样本量计算；无「设计类型 → 方法集」的强制分级 |
| G3 前提检验 | ✅ | 正态性、方差齐性、球形性（未校正但三处标注） |
| G4 效应量与区间 | ✅ | Cohen's d、HR 与 95%CI、率差、bootstrap 中位数差、t 临界值区间 |
| G5 稳健性 | 🟡 | 缺失 delta 扫描、PH 假设检查；无 tipping point、无完整 MI 敏感性 |
| G6 多重性 | 🟡 | 7 种校正（SNK/Tukey/Dunnett/LSD/Schéffé/Holm/Bonferroni）；Hochberg、gatekeeping、图形法未实现 |
| G7 可复现 | ✅ | Dunnett、MICE、bootstrap 全部固定随机种子 |

### 教材对齐边界

教材 demo 覆盖第一至十一、十四、十五章；**第十二、十三章未收录**。
因此剩余缺口多数不是「教材要求但未做」，而是「教材未覆盖 + 顶刊门禁要求」的方法。
继续按章节补的边际收益已很低，后续应改为按门禁驱动。

## 4. 022–029 修掉的六类缺陷

| # | 现象 | 修正 | 依据 |
|---|---|---|---|
| 1 | 均值差 95%CI 固定用 `1.96×SE`，n=6/组时区间偏窄约 15% | 改 t 临界值，自由度按合并方差 / Welch–Satterthwaite / 配对 n−1 区分 | 小样本必须用 t 分布 |
| 2 | 配对 t 检验对**两组原始值**做 Shapiro，导致错选 Mann-Whitney U | 改为检验**差值**，非正态降级为 Wilcoxon 符号秩 | 配对设计的前提是差值正态 |
| 3 | 1009 例数据中年龄偏度 −0.16 却因 Shapiro P=4.6e-07 被判偏态 | n≥500 时以偏度为主判据；单一取值占比 >50% 直接判偏态 | 大样本下 Shapiro 对微小偏离过度敏感 |
| 4 | 新增 `survival_curve` 时只改 `CHART_TYPES`，漏改 `ChartType` 字面量，`PlanStep` 在 pydantic 阶段被拒 | 补 `ChartType == CHART_TYPES` 一致性测试 | 与 023 的 `MethodType` 漏改同类 |
| 5 | `PHReg.llr` 返回 `None`；`schoenfeld_residuals` 是属性不是方法 | 手建零模型算 `2*(llf−llf_null)`；属性/方法双兼容 | statsmodels 接口与直觉不符 |
| 6 | `planned` 列表滞后：`multiple_imputation` 曾写「MICE 多重插补」而实际不存在；`multiplicity_control` 写「Holm/Dunnett 未实现」而 025 已实现 | 改写为「已实现 X；未实现 Y」格式，并加契约测试强制声明未实现范围 | 能力披露是产品承诺，滞后等于误导 |

## 5. 剩余缺口

**方法学**

- 竞争风险（Fine–Gray）、时依协变量、分层 Cox、参数生存模型、左截断。
- 完整多重插补（Rubin 合并）、MMRM、tipping point、MNAR 选择模型、纵向缺失。
- 球形性校正（Mauchly / Greenhouse–Geisser）、混合设计（组间+组内）。
- Hochberg、层级 gatekeeping、图形法、期中 α 消耗。
- 三因素及以上交互、裂区设计；非劣效/等效设计与整群随机的样本量。
- 频数表加权描述（仅无原始数据时使用）；Logistic 完美分离的 Firth 惩罚回归。

**工程**

- 会话仅存内存，重启丢失；WS 无断线重连与历史回放。
- 无上传大小/行数限额，解析在主事件循环同步执行。
- `print` 未全面替换为 `logging`；无 ruff/mypy；前端无路由级分包与错误边界。
- 分支保护需在 GitHub 后台手动开启；CI 不接真实模型。

## 6. 下一步

| 优先级 | 事项 | 理由 |
|---|---|---|
| P1-1 | 会话持久化 + WS 断线重连 + 历史回放（030 之后编号） | 内部使用最痛；不依赖统计能力 |
| P1-2 | 数据清洗层（去重、异常值、标准化、分箱、子集） | 上传后的第一道刚需 |
| P1-3 | 完整多重插补 + MMRM | 缺失路径的最后一公里 |
| P2 | 结构化日志、ruff/mypy、前端分包与错误边界 | 长期可维护性 |

## 附录 A：本次（030）变更

| 文件 | 变更 |
|---|---|
| `backend/src/medsta/api/routes_capabilities.py` | `competing_risk`、`multiplicity_control` 描述改写为「已实现 / 未实现」 |
| `backend/tests/test_capabilities.py` | 新增 3 条能力披露契约测试 |
| `docs/evaluation-report.md` | 重写为 029 基线 |
| `docs/timeline.md` | 新增本轮三条记录 |
| `docs/design-notes.md` | 追加「能力披露必须写明未实现范围」 |
| `.gitignore` | 忽略 `docs/*.pdf`（31MB 教材 PDF 不入库） |
| `TO_DO.md`、`CODEBUDDY.md` | 用例数与已知限制同步 |

## 附录 B：关键回归命令

```bash
# 后端全量 + 覆盖率门槛
cd backend && python -m pytest --cov=medsta --cov-fail-under=83

# 前端组件与构建
cd frontend && npm test -- --run && npm run build && npm run lint

# 浏览器 E2E
cd frontend && npm run test:e2e

# 真实模型冒烟（默认跳过，消耗额度）
cd backend && MEDSTA_REAL_LLM=1 python -m pytest tests/test_real_llm_smoke.py -q
```

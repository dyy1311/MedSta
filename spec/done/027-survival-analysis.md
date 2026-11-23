# 027 - 生存分析族（KM / log-rank / Breslow / Cox / RMST）

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

项目此前只有横断面分析，无法处理「随访时间 + 结局事件 + 删失」的资料。
《医学统计学》第 8 版**第十四章 生存分析**（第 145 页起）提供了完整口径，
本 spec 据此补齐 KM 曲线、组间比较与 Cox 回归。

> **事实更正**：024/025 两轮曾判断「教材无生存分析」，实为只读到第十五章前的目录而漏检。
> 教材实际有 16 处「生存分析」、8 处「Kaplan-Meier」、30 处「Cox」、7 处「Breslow」。
> 但 **RMST、Schoenfeld 检验、竞争风险均为 0 处**，这三项需外部标准或标 planned。

## 范围

- 做：右删失、KM 估计（Greenwood SE + CI 截断 + 中位生存期）、风险人数表、log-rank、Breslow、Cox PH（HR/CI/LR/Wald/Score）、RMST、Schoenfeld 残差检查、生存曲线图。
- 不做：竞争风险与 Fine–Gray、时依协变量、分层 Cox（strata）、参数生存模型（Weibull/exponential）、寿命表法、区间删失、左截断。

## 教材依据

| 内容 | 教材位置 |
|---|---|
| 生存时间、右删失、`S(t)`、中位生存期、风险函数 | §14-1（6104–6161），公式 14-1~14-3 |
| KM 乘积极限、排序规则、`n_i`、`q_i/p_i` | §14-2（6163–6197），公式 14-4/14-5 |
| Greenwood 标准误 | §14-2（6199–6205），公式 14-6 |
| 生存率 CI 及末端越界处理 | §14-2（6207–6213），公式 14-7 |
| log-rank 检验 | §14-2（6229–6243），公式 14-8/14-9 |
| Breslow 检验 | §14-2（6227 提及，广义 Wilcoxon） |
| Cox 模型、HR、偏似然、三种检验 | §14-3（6313–6383），公式 14-11~14-15 |
| 例 14-2 数据（15 + 21 例，含删失） | 6175 |
| 表 14-2 逐时间点 S(t) 与 SE | 6217 |

**教材未给**（须标注外部来源）：RMST、Schoenfeld 残差检验。**竞争风险**教材 0 处提及，保持 planned。

## 行为列表（TDD 循环队列）

- [x] B1: KM 逐时间点生存率复现表 14-2 的 15 个值（0.933/0.862/0.790/0.711/0.632/0.553/0.474/0.379/0.253）
- [x] B2: KM 的 Greenwood 标准误复现表 14-2（0.064/0.091/0.108/0.123/0.132/0.137/0.139/0.140/0.139）
- [x] B3: 同一时间点完全数据排在删失数据之前（教材 §14-2 规则）
- [x] B4: 中位生存期：生存率降至 50% 时插值；未达到时返回 `None` 并给说明
- [x] B5: 生存率 CI 截断到 [0,1] 并标记 `ci_truncated`
- [x] B6: 输出风险人数表（时间区间 × 期初人数 × 事件数 × 删失数）
- [x] B7: log-rank 两组检验输出 χ²、df=1、p
- [x] B8: log-rank 多组（g≥3）用 g−1 维二次型，χ² 与手算一致
- [x] B9: Breslow 权重为 `n_i`，与 log-rank 在同一数据上给出不同 χ²
- [x] B10: Cox 的 β、HR、HR 95%CI 与 `PHReg` 直接调用一致
- [x] B11: Cox 整体 LR 检验 `2*(llf_full − llf_null)` 与手算一致
- [x] B12: 每个协变量的 Wald χ² 与 p 输出
- [x] B13: Score 检验可用时输出，不可用时明确标注而非伪造数值
- [x] B14: Schoenfeld 残差与时间的 Spearman 相关输出 rho/p，p<0.05 时提示违反 PH 假定
- [x] B15: RMST 用梯形积分，τ 默认取各组最大随访最小值，输出差值与 95%CI
- [x] B16: 事件列非 0/1 时报可读错误
- [x] B17: 全删失（事件数=0）时报可读错误
- [x] B18: 时间为负值时报可读错误
- [x] B19: 新增 `survival_curve` 图表：阶梯曲线 + 删失标记 + 多组图例
- [x] B20: `/capabilities` 中 `survival_analysis` 进入 tools，`planned` 不再包含它

## 验收标准

- [硬门] B1–B20 均有确定性测试，先确认 RED 再最小实现
- [硬门] 表 14-2 的 15 个时间点 S(t) 与 SE 全部对齐（教材三位小数，容差 1e-3）
- [硬门] Cox 与 `PHReg` 的 β/HR/CI/p 在 1e-6 内一致；LR 检验与 `2*(llf−null_llf)` 一致
- [硬门] 多组 log-rank 不得退化为「只对第一组求和」
- [硬门] 后端 `pytest` 全绿且覆盖率 ≥83%；前端 `vitest`/`build`/`lint` 全绿；E2E 2 项不回归
- [软标] `method_note` 能说清「删失不是缺失值」与「PH 假定未检验的风险」
- [软标] 中位生存期未达到时的说明让非统计专业用户也能理解

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1/B2/B3/B5/B6 | `survival.km_estimate` | `test_survival.py::test_km_matches_table_14_2` 等 |
| B4 | 同上 | `test_survival.py::test_median_reached_and_unreached` |
| B7/B8/B9 | `survival.logrank_test` | `test_survival.py::test_logrank_two_groups` / `test_logrank_multi_group_quadratic` / `test_breslow_weights` |
| B10/B11/B12/B13/B14 | `survival.cox_fit` | `test_survival_cox.py` |
| B15 | `survival.rmst` | `test_survival_cox.py::test_rmst_trapezoid` |
| B16/B17/B18 | `survival.survival_analysis` | `test_survival_edges.py` |
| B19 | `plotting.render_chart` | `test_survival_edges.py::test_survival_curve_rendered` |
| B20 | `GET /capabilities` | `test_capabilities.py` |

### 关键字段

| 字段 | 位置 | 说明 |
|---|---|---|
| `points[]` | KM | `time/n_at_risk/events/censored/survival/se/ci_low/ci_high` |
| `median_survival` | KM | 未达到时为 `None` |
| `median_survival_note` | KM | 未达到时的可读说明 |
| `ci_truncated` | KM | CI 是否被截断到 [0,1] |
| `chi2/df/p_value/method` | log-rank | `method` ∈ `logrank/breslow` |
| `coefficients[]` | Cox | `term/coef/se/hr/ci_low/ci_high/wald_chi2/p_value` |
| `lr_test` | Cox | `chi2/df/p_value` |
| `score_test` | Cox | 不可用时为 `None` 且 `note` 说明 |
| `ph_check[]` | Cox | `term/rho/p_value/violated` |
| `rmst/rmst_diff` | RMST | τ、各组 RMST、差值及 CI |

## 依赖与影响

- `stats/survival.py`（新增）：`km_estimate`、`logrank_test`、`cox_fit`、`rmst`、`survival_analysis`（handler）。
- `stats/registry.py`：注册 `survival_analysis`；`CHART_TYPES` 增 `survival_curve`；`_TASK_META`/`_SLOT_META` 补条目。
- `stats/plotting.py`：`CHART_LABELS`、`render_chart` 新增分支、`default_chart_for` 映射。
- `stats/notes.py`：新增方法说明（教材第十四章 + RMST/PH 外部来源）。
- `agents/discussion.py`：`MethodType` 增 `survival_analysis`。
- `agents/interpretation.py`：`_SIMPLE_KEYS` 增生存分析结论键。
- `api/routes_capabilities.py`：`_PLANNED` 移除 `survival_analysis`（原描述「需引入 lifelines」错误），新增 Fine–Gray planned。
- 文档：`statistics-methods.md`、`design-notes.md`、`timeline.md`、`TO_DO.md`、`CODEBUDDY.md`。

## 备注

- **排序规则**：`sort_values(["time", "event"], ascending=[True, False])`，保证同时间点事件在前、删失在后（教材 6179）。
- **Greenwood 除零**：`n_j == d_j` 时该累加项跳过，SE 取 0；不抛异常。
- **CI 截断**：`max(0, low)`、`min(1, high)`，并置 `ci_truncated=True`。
- **PHReg 的 llr 为 None**：整体 LR 必须手建零模型 `PHReg(t, ones, status=e).fit()`，取 `2*(llf_full − llf_null)`。
- **Score 检验**：优先取 `m.score`；若接口不可用则输出 `None` + 说明，不伪造。
- **多组 log-rank**：构造 `(g−1)` 维 `O−E` 向量与协方差矩阵，求 `(O−E)ᵀ V⁻¹ (O−E)`；只对第一组求和会系统性偏大。
- **RMST 的 τ**：默认 `min(各组最大随访时间)`；若 τ 超过某组最大随访，标记 `truncated=True`。

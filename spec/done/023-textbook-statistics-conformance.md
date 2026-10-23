# 023 - 按教材校准统计工具链（描述 / 参考值范围 / 相关与回归）

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

项目统计层的方法选择逻辑完整，但数值口径与指标覆盖未按教材校准。依据
`docs/Medical_Statistics_LiKang_8ed_demo.clean.md`（《医学统计学》第 8 版，李康、贺佳，
第二、三、十一章）逐条核对后确认三类问题：

1. **现有结果不严谨**：均值差 95%CI 固定用 1.96；配对 t 检验对原始值而非差值做正态性检验；
   工具目录声称输出标准差但实现缺失。
2. **教材要求的基础指标缺失**：标准差、IQR、极差、变异系数、几何均数、众数；
   以及第三章的医学参考值范围（正态法/百分位数法/对数正态法）。
3. **解释缺失教材口径**：相关分析没有强度分档与「相关不等于因果」提示，
   回归没有方差分析表与残差诊断，各方法输出没有教材依据说明。

> 边界：该 demo 仅收录第一、二、三、十一、十五章，t 检验/方差分析/卡方正文不在其中，
> 因此不据教材改动这些方法的**检验选择逻辑**，只修与通用原理冲突的准确性缺陷。

## 范围

- 做：均值差 CI 的 t 临界值、配对差值正态性、非参数中位数差 + bootstrap 区间；`descriptive_stats`（新）；`reference_range`（新）；相关强度/r²/因果提示；回归方差分析表与残差诊断；`method_note` 全方法覆盖与前端展示；`MethodType` 与注册表一致性契约测试。
- 不做：`describe` 输出结构改动（画像与导出零波及）；频数表加权法（无原始数据场景）；Kendall 相关；参考值范围的界值标注图；Firth 惩罚；生存/缺失数据（属 P0 其他项）。

## 行为列表（TDD 循环队列）

- [x] B1: 均值差 95%CI 用 t 临界值（Welch 用 Welch–Satterthwaite 自由度，配对用 `n_pairs−1`），结果含 `df`、`t_critical`、`ci_method`
- [x] B2: `paired=True` 时对**差值**做 Shapiro 正态性检验，策略链文案明确为「差值正态性」
- [x] B3: Mann-Whitney 路径输出中位数差与 bootstrap 95%CI（固定种子），不输出基于均值的伪 CI
- [x] B4: `classify_distribution` 四态判定：`insufficient`（n<3）/`normal`（|skew|≤1 且 Shapiro p>α）/`log_normal`（非正态、全正、对数后正态）/`skewed`
- [x] B5: `descriptive_stats` 逐列输出 n/mean/sd/cv/median/q25/q75/iqr/min/max/range/mode/skewness/geometric_mean/distribution/recommended/reason
- [x] B6: 几何均数仅在全部为正时计算，含 0 或负值置 `None` 并说明；同一资料 `G ≤ mean`
- [x] B7: `descriptive_stats` 支持 `group_by` 分层，逐组同结构并给各组样本量
- [x] B8: `reference_range` 正态法双侧 95%：例 3-3（x̄=4.78, s=0.38）→ (4.04, 5.52)
- [x] B9: `reference_range` 百分位数法支持 90/95/99 与双侧/单侧下限/单侧上限
- [x] B10: `reference_range` 对数正态法：对数变换后计算再取反对数还原（对齐例 3-4 单侧上限）
- [x] B11: `reference_range` 样本量警示：n<30 正态法警示；百分位数法 n<100 警示
- [x] B12: `correlation` 每对输出 `r_squared` 与 `strength`（≤0.3 较差 / 0.3–0.6 中度 / 0.6–0.8 较高 / >0.8 很高），顶层输出固定 `causality_note`
- [x] B13: `regression` 输出 `anova_table`，满足 `ss_total ≈ ss_regression + ss_residual` 与 `f_value = ms_regression / ms_residual`
- [x] B14: `regression` 输出 `diagnostics`：残差 Shapiro p、Breusch–Pagan p、`n < 10k` 过拟合提示
- [x] B15: 每个方法结果附 `method_note`（教材章节与公式编号、适用条件、解读禁忌），由宿主写入
- [x] B16: `MethodType` 字面量集合与注册表键集合严格一致（新增方法漏改即测试失败）
- [x] B17: 前端审阅卡每步可折叠展示「方法依据」，无 `method_note` 时不渲染
- [x] B18: `/capabilities` 披露 `descriptive_stats` 与 `reference_range`（含参数与图表）

## 验收标准

- [硬门] B1–B18 均有确定性测试，先确认 RED 再最小实现
- [硬门] 教材例题数值复现：例 2-6（s=19.49/2.88）、例 2-8（CV=13.81%/13.91%）、例 2-2（G≈209）、例 3-3（4.04/5.52）、例 11-2（r≈0.801）
- [硬门] `describe` 输出结构与前端画像列不变；`ci95` 键名保留（仅数值口径修正）
- [硬门] 后端 `pytest` 全绿且覆盖率不低于 83%；前端 `vitest`/`build`/`lint` 全绿；E2E 2 项不回归
- [硬门] 结果数值可复现：bootstrap 固定种子，`sd` 用 `ddof=1`
- [软标] `method_note` 文案能让人看懂「这个数怎么来的、什么时候不该用」
- [软标] `recommended` 与 `reason` 能让非统计专业用户理解为何选 x̄±s 而非 M(P25~P75)

## 契约与测试映射

### 分布判定（宿主确定性）

| 条件 | `kind` | `recommended` |
|---|---|---|
| n < 3 | `insufficient` | `""`（只给 n/min/max） |
| \|skew\| ≤ 1 且 Shapiro p > α | `normal` | `x̄±s` |
| 非正态、全为正、`log` 后 Shapiro p > α | `log_normal` | `G` |
| 其余 | `skewed` | `M(P25~P75)` |

补充：含 0 或负值不计算 G，`reason` 注明；`cv` 在 `mean≈0`（\|mean\| < 1e-12）时置 `None`。

### 参考值范围（对齐教材表 3-1）

| percentage | 双侧 | 单侧下限 | 单侧上限 | 百分位双侧 |
|---|---|---|---|---|
| 90 | x̄±1.64S | x̄−1.28S | x̄+1.28S | P5~P95 |
| 95 | x̄±1.96S | x̄−1.64S | x̄+1.64S | P2.5~P97.5 |
| 99 | x̄±2.58S | x̄−2.33S | x̄+2.33S | P0.5~P99.5 |

z 值由 `scipy.stats.norm.ppf` 计算（比查表更精确），输出保留 4 位；测试按教材四舍五入比对。

### 字段契约

| 字段 | 位置 | 说明 |
|---|---|---|
| `ci95` | `group_compare.result` | 保留键名，数值改为 t 临界值口径 |
| `df` / `t_critical` / `ci_method` | 同上 | 新增，标明区间来源 |
| `median_diff` / `ci_method="bootstrap"` | 同上（非参数路径） | 中位数差与 2000 次 bootstrap 百分位区间 |
| `r_squared` / `strength` | `correlation.pairs.<pair>` | 决定系数与教材分档 |
| `causality_note` | `correlation` 顶层 | 固定文案 |
| `anova_table` | `regression` | ss/df/ms/f 分解 |
| `diagnostics` | `regression` | 残差正态、等方差、样本量提示 |
| `method_note` | 各方法顶层 | 教材口径说明（≤120 字） |

### 行为 → 测试

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `stats.methods.group_compare` | `test_stats_methods.py::test_mean_diff_ci_uses_t_critical_value` |
| B2 | 同上 | `test_stats_methods.py::test_paired_uses_difference_normality` |
| B3 | 同上 | `test_stats_methods.py::test_mannwhitney_reports_median_diff_bootstrap` |
| B4 | `stats.descriptive.classify_distribution` | `test_textbook_conformance.py::test_distribution_classification_four_states` |
| B5 | `stats.descriptive.descriptive_stats` | `test_textbook_conformance.py::test_descriptive_outputs_full_metrics` |
| B6 | 同上 | `test_textbook_conformance.py::test_geometric_mean_requires_positive_values` |
| B7 | 同上 | `test_textbook_conformance.py::test_descriptive_grouped_layers` |
| B8 | `stats.descriptive.reference_range` | `test_textbook_conformance.py::test_reference_range_normal_matches_example_3_3` |
| B9 | 同上 | `test_textbook_conformance.py::test_reference_range_percentile_sides` |
| B10 | 同上 | `test_textbook_conformance.py::test_reference_range_log_normal_restores_scale` |
| B11 | 同上 | `test_textbook_conformance.py::test_reference_range_small_sample_warnings` |
| B12 | `stats.methods.correlation` | `test_stats_methods.py::test_correlation_strength_and_r_squared` |
| B13 | `stats.methods.regression` | `test_stats_methods.py::test_regression_anova_table_identity` |
| B14 | 同上 | `test_stats_methods.py::test_regression_diagnostics_reported` |
| B15 | 各 handler 结果 | `test_textbook_conformance.py::test_every_tool_has_method_note` |
| B16 | `agents.discussion.MethodType` vs `stats.registry` | `test_method_contract.py::test_method_literal_matches_registry` |
| B17 | `ReviewCard` | `ReviewCard.methodNote.test.tsx` |
| B18 | `GET /capabilities` | `test_capabilities.py::test_capabilities_lists_textbook_tools` |

## 依赖与影响

- `stats/descriptive.py`（新增）：`classify_distribution`、`descriptive_stats`、`reference_range`、`_geometric_mean`、`_modes`。
- `stats/notes.py`（新增）：`METHOD_NOTES` 单一文案源。
- `stats/methods.py`：`group_compare` 区间与配对前提；`correlation` 强度/r²/因果提示；`regression` 方差分析表与诊断；各方法挂 `method_note`。
- `stats/registry.py`：注册两个新工具；修正 `describe` 描述文案；补 `_TASK_META`/`_SLOT_META`。
- `agents/discussion.py`：`MethodType` 增补两个名称（由 B16 契约测试守护）。
- `agents/interpretation.py`：`_SIMPLE_KEYS` 增补新方法键；证据包纳入 `method_note`。
- `frontend/src/chat/ReviewCard.tsx`：`method_note` 折叠展示。
- 文档：`docs/statistics-methods.md`（方法口径与教材对应）、`docs/timeline.md`、`TO_DO.md`、`docs/design-notes.md`。

## 备注

- **分位数口径**：使用 pandas 默认线性插值，等价于软件基于原始数据的精确计算；教材公式（2-7）为频数表近似，仅在无原始数据时适用，spec 明确不实现加权法。
- **相关强度**：边界按教材 §11 注意事项 2；例 11-2 的 r=0.801 恰在 0.8 边界，正文称「较高」而分档规则为「很高」，测试只断言 r≈0.801，分档用非边界数据验证。
- **bootstrap**：2000 次、`np.random.default_rng(20261023)`，保证跨平台可复现。
- **method_note 归属**：宿主固定文案，不是模型输出；长度 ≤120 字，避免挤占审阅卡。
- **既有断言影响**：`ci95` 数值变化会波及 `test_stats_methods.py` 中依赖 1.96 的断言，需同步更新而非放宽容差。

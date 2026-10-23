# 024 - 对齐教材第六至十章：参数估计 / t 检验 / 方差分析 / χ² / 秩和

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

spec 023 只覆盖了教材第二、三、十一章。本次核对第六至十章（参数估计与假设检验、t 检验、
方差分析、χ² 检验、非参数秩和检验）后确认：项目在**方法覆盖**与**判定口径**两方面均有缺口。

1. 缺失方法：单样本检验、随机区组设计方差分析、配对四格表 McNemar、Kendall τ。
2. 口径不一致：配对 t 仍做方差齐性检验（教材明确不需要）；两独立样本方差齐性用 Levene α=0.05
   （教材用 F 检验、α=0.10）；ANOVA 事后用 Welch t + Holm（教材用 SNK-q）；四格表按期望频数
   比例降级（教材按 n 与 T 三档）。
3. 缺失输出：ANOVA 事后无区间估计；分组率无置信区间（教材 §6 第四节要求报告区间）。

## 范围

- 做：单样本 t / Wilcoxon、随机区组 ANOVA、McNemar、Kendall τ；F 检验口径与配对跳过方差齐性；SNK-q 与 Dunn 事后；四格表三档；χ² 分割法两两比较；分组率 CI；单双侧参数；真实数据夹具。
- 不做：样本量与检验效能计算（教材只讲概念）、两率差 CI、Bartlett 检验（用 Levene 替代并注明）、Tukey/Dunnett/LSD（提供 SNK 与 Holm 两条即可）、条件 logistic、生存分析。

## 行为列表（TDD 循环队列）

- [x] B1: 两独立样本方差齐性用 F 检验（`F=S²大/S²小`，α=0.10），例 7-4 F=5.402 判方差不齐
- [x] B2: 配对设计跳过方差齐性检验，策略链注明「配对不要求两组方差齐性」
- [x] B3: 单样本 t（例 7-1：n=35、x̄=3.42、S=0.40、μ0=3.30 → t=1.77，P>0.05），并输出均数 95%CI
- [x] B4: 单样本非正态降级 Wilcoxon 符号秩，`test` 可强制 auto/t/wilcoxon
- [x] B5: `sides` 支持 two/greater/less，单侧 p 值为双侧一半且方向匹配
- [x] B6: 随机区组 ANOVA 满足 `SS总 = SS处理 + SS区组 + SS误差` 与自由度分解
- [x] B7: 随机区组 ANOVA 输出处理效应与区组效应的 F/p，误差均方用于事后比较
- [x] B8: ANOVA 事后默认 SNK-q（例 8-3：q=5.04/3.27/1.77，界值 3.52/2.91，跨度 a=3/2/2）
- [x] B9: SNK 逐步规则：跨度最大的比较不显著时，更小跨度不再判为显著；原始 p 值仍保留
- [x] B10: `correction=holm/bonferroni` 仍可用，输出列与 SNK 一致
- [x] B11: Kruskal-Wallis 事后用 Dunn 检验 + Bonferroni，`method_note` 标注教材未给公式
- [x] B12: 四格表三档判定——n≥40 且 T≥5 专用公式；n≥40 且 1≤T<5 校正；n<40 或 T<1 Fisher
- [x] B13: 配对四格表 McNemar（例 9-4：b=24、c=20 → χ²=0.364，P>0.05）
- [x] B14: McNemar 校正公式：b+c<40 时用 `(|b−c|−1)²/(b+c)`
- [x] B15: 多个样本率两两比较（χ² 分割 + Bonferroni），支持 all_pairs / vs_control 两种 α′
- [x] B16: R×C 整体检验（例 9-5：χ²=22.809，ν=2）保持不变
- [x] B17: 分组率输出 95%CI（n≥40 用 Wald，n<40 用 Wilson）
- [x] B18: `correlation` 支持 `kendall`（τ-b，处理 ties），强度分档沿用 023
- [x] B19: 新增三个方法进入 `MethodType` 与 `/capabilities`，一致性测试通过
- [x] B20: 基线数据夹具（60 行、5 个手术方式组）可完成多组比较与卡方，不依赖 docs 路径

## 验收标准

- [硬门] B1–B20 均有确定性测试，先确认 RED 再最小实现
- [硬门] 教材例题复现：例 7-1（t=1.77）、7-2（t=3.738）、7-4（F=5.402）、7-5（t′=7.018, ν′=14.687）、8-3（q=5.04/3.27/1.77）、9-4（χ²=0.364）、9-5（χ²=22.809）、10-5（Hc=12.27）
- [硬门] 现有输出键只增不改：`anova.pairwise.statistic` 保留；`chi_square.correction` 布尔入参归一化为 yes/no
- [硬门] 后端 `pytest` 全绿且覆盖率 ≥83%；前端 `vitest`/`build`/`lint` 全绿；E2E 2 项不回归
- [硬门] 夹具 CSV 从 `tests/fixtures` 读取，测试不访问 `docs/`
- [软标] `method_note` 能说明「教材用 F 检验/SNK，软件常用 Levene/Holm」的取舍
- [软标] 四格表三档的策略链能让人看懂为什么走了 Fisher

## 契约与测试映射

### 判定口径

| 场景 | 教材依据 | 实现口径 |
|---|---|---|
| 两独立方差齐性 | §7-6，F 检验，α=0.10 | `F=S²大/S²小`，双侧 p，α=0.10 |
| 配对正态性 | §7 注意事项 2 | 只检差值，**不做**方差齐性 |
| ANOVA 事后 | §8-4，SNK-q | `q=|x̄A−x̄B|/√(MS误差/2·(1/nA+1/nB))`，`studentized_range.sf(q, span, df)` |
| K-W 事后 | §10 教材未给 | Dunn + Bonferroni，标注来源 |
| 四格表 | §9-1 | n≥40&T≥5 专用；n≥40&1≤T<5 校正；n<40 或 T<1 Fisher |
| 配对四格表 | §9-2 | `(b−c)²/(b+c)`，b+c<40 用校正 |
| 多样本率 | §9-3 二 | χ² 分割，α′=α/C(k,2) 或 α/(k−1) |

### 新增工具

| 工具 | 参数 | 输出 |
|---|---|---|
| `one_sample_test` | `mu0`(number,必填)、`test`(auto/t/wilcoxon)、`sides`(two/greater/less) | `t`/`df`/`p_value`、`mean`/`sd`/`n`、`ci95`、`strategy` |
| `randomized_block_anova` | `group_column`、`block_column` | `ss_treatment`/`ss_block`/`ss_error`、`df_*`、`ms_error`、`f_treatment`/`p_treatment`、`f_block`/`p_block` |
| `mcnemar_test` | `row_column`、`col_column` | `a`/`b`/`c`/`d`、`chi2`、`corrected`、`p_value`、`agreement_rate` |

### 行为 → 测试

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `methods.group_compare` / `methods._f_variance_test` | `test_textbook_ch6_10.py::test_f_variance_matches_example_7_4` |
| B2 | `methods.group_compare` | `test_textbook_ch6_10.py::test_paired_skips_variance_test` |
| B3 | `inference.one_sample_test` | `test_textbook_ch6_10.py::test_one_sample_t_matches_example_7_1` |
| B4 | 同上 | `test_inference.py::test_one_sample_falls_back_to_wilcoxon` |
| B5 | 同上 | `test_inference.py::test_one_sided_p_value_direction` |
| B6 | `inference.randomized_block_anova` | `test_inference.py::test_block_anova_sum_of_squares_identity` |
| B7 | 同上 | `test_inference.py::test_block_anova_reports_treatment_and_block` |
| B8 | `methods.anova` | `test_textbook_ch6_10.py::test_snk_matches_example_8_3` |
| B9 | `significance.snk_q_pvalue` | `test_inference.py::test_snk_step_down_rule` |
| B10 | `methods.anova` | `test_inference.py::test_anova_holm_still_available` |
| B11 | `methods.anova` | `test_inference.py::test_kruskal_dunn_posthoc` |
| B12 | `methods.chi_square` | `test_textbook_ch6_10.py::test_fourfold_table_three_tiers` |
| B13 | `inference.mcnemar_test` | `test_textbook_ch6_10.py::test_mcnemar_matches_example_9_4` |
| B14 | 同上 | `test_inference.py::test_mcnemar_corrected_when_b_plus_c_small` |
| B15 | `methods.chi_square` | `test_inference.py::test_multi_rate_pairwise_bonferroni` |
| B16 | `methods.chi_square` | `test_textbook_ch6_10.py::test_rxc_matches_example_9_5` |
| B17 | `methods.chi_square` | `test_inference.py::test_group_rate_confidence_interval` |
| B18 | `methods.correlation` | `test_textbook_ch6_10.py::test_kendall_tau_reported` |
| B19 | `MethodType` + `/capabilities` | `test_method_contract.py`（既有）+ `test_capabilities.py` |
| B20 | 夹具 CSV | `test_textbook_ch6_10.py::test_baseline_fixture_runs_group_compare` |

## 依赖与影响

- `stats/inference.py`（新增）：三个方法与 `_f_variance_test` 共用工具。
- `stats/significance.py`：`snk_q_pvalue`、`dunn_pvalue`、`bonferroni_alpha`。
- `stats/methods.py`：`group_compare`（F 检验、配对跳过、sides）、`anova`（SNK/Dunn）、`chi_square`（三档、pairwise、rates）、`correlation`（kendall）。
- `stats/registry.py`：注册三个新工具；`correction` 改 choice；`correlation.method` 增 kendall。
- `stats/notes.py`、`agents/discussion.py`、`agents/interpretation.py`、`frontend/src/types.ts`（method 为 string，无需改）。
- 测试：`test_textbook_ch6_10.py`、`test_inference.py`、`fixtures/baseline_sample.csv`、`test_stats_methods.py` 同步。
- 脚本：`scripts/derive_baseline_fixture.py`、`scripts/smoke_baseline.py`。
- 文档：`docs/statistics-methods.md`、`docs/design-notes.md`、`docs/timeline.md`、`TO_DO.md`、`CODEBUDDY.md`。

## 备注

- **教材 vs 软件默认的取舍**：两独立方差齐性按教材用 F 检验（α=0.10），`levene_test` 工具保留并改为 α=0.10，用于多组或非正态；ANOVA 事后默认 SNK-q，Holm 保留；这些取舍写进 `design-notes.md`，不静默替换。
- **多组秩和事后**：教材 §10 明确「具体比较方法请参考相关书籍」，故采用通用 Dunn + Bonferroni，并在 `method_note` 标注来源，不冒充教材口径。
- **SNK 逐步规则**：保留全部原始 p 值，`significant` 按逐步规则给出并附 `step_down` 标记，避免用户误读「p<0.05 但被判不显著」。
- **兼容性**：`anova.pairwise` 保留 `statistic` 键（写入 q 或 U）；`chi_square.correction` 由 boolean 改为 choice，`normalize_params` 把 True/False 映射为 yes/no。
- **性能**：1009 行、5 组的比较为 O(k²)，无迭代；SNK 与 Dunn 均为闭式计算。
- **夹具**：`utf-8-sig` 编码（与上传解析一致），60 行、5 组各 12 例，保留全部 22 列。

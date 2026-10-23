# 025 - 补全教材只列名称的事后比较、析因/重复测量与样本量效能

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

教材第六至十章核对结果表明，下列七项**只有名称、适用范围或概念，没有公式与例题**：

| 项目 | 教材实际内容 | 行号 |
|---|---|---|
| Tukey / Dunnett / LSD-t / Scheffé | 仅表 8-9 方法选择表各一行 | 3613 |
| 析因设计 | 练习题选项 + 第十五章临床试验设计概念 | 3785、6931、6941 |
| 重复测量 | 练习题选项 + 「精密度」定义中的字面用法 | 3815、6821 |
| 样本量与检验效能 | 检验效能 20 处均为 1−β 概念；样本含量 23 处均为定性描述 | 2839–2843 |

教材 3615 明言「以 SNK 法为例」，4170 明言「仅介绍 χ² 分割法」，即其余方法未展开。
本 spec 依据外部标准补全，并在方法说明中标注来源，不冒充教材口径。

## 范围

- 做：`anova` 事后扩展 Tukey HSD / Dunnett / LSD-t / Scheffé（保留 SNK/Holm/Bonferroni）；`factorial_anova`（两因素 + 一阶交互）；`repeated_measures_anova`（单因素组内）；`sample_size`（六种设计 × n/power 双向）；scipy 下限提升至 1.14。
- 不做：三因素及以上交互、裂区设计、混合设计重复测量、球形性校正（Greenhouse-Geisser/Huynh-Feldt）、缺失数据、样本量的非劣效/等效设计。

## 外部依据

| 方法 | 依据 |
|---|---|
| Tukey HSD | Tukey's range test（Wikipedia）：studentized range 分布；Tukey-Kramer 支持不等样本量，`q=diff/√(MSE/2·(1/ni+1/nj))`，p=`studentized_range.sf(q, k, df)`，k 固定为组数 |
| Dunnett | Dunnett 1955 单步检验（多元 t 分布，off-diagonal 相关约 1/2）；`scipy.stats.dunnett`（scipy≥1.14 内置，docs.scipy.org） |
| LSD-t | 最小显著差异：成对合并方差 t，不做多重性校正（教材表 8-9 亦注明只适合预设对） |
| Scheffé | F 分布全族比较：`F=diff²/(MSE·(1/ni+1/nj)·(k−1))`，p=`f.sf(F, k−1, df)`；比 Tukey 保守（stattrek） |
| 析因设计 | `SS总=SS(A)+SS(B)+SS(AB)+SS误差`（ScienceDirect topics: Interaction Effect） |
| 重复测量 | `SS总=SS时间+SS受试者+SS误差`（ScienceDirect topics: Repeated Measure Analysis） |
| 样本量 | 两独立均数每组 `n=2σ²(z_{α/2}+z_β)²/δ²`；α=0.05、power=0.8 时 `n≈15.7/d²`（d=0.5→64、0.8→26、1.0→17）；实现用 `statsmodels.stats.power` |

## 行为列表（TDD 循环队列）

- [x] B1: Tukey HSD 用固定 k 求 studentized range p 值，与 `statsmodels.pairwise_tukeyhsd` 一致（Tukey-Kramer 允许不等样本量）
- [x] B2: Dunnett 仅产出「对照 vs 各试验组」的行，p 值与 `scipy.stats.dunnett` 一致
- [x] B3: Dunnett 未给 `control_group` 时报可读错误并列出全部组名，不静默取第一组
- [x] B4: LSD-t 用合并方差 t、自由度 `N−k`、不做校正
- [x] B5: Scheffé 的 p 值恒 ≥ Tukey 的 p 值（更保守）
- [x] B6: 七种 `correction` 统一输出列（`group_a/group_b/mean_diff/statistic/p_value/adjusted_p/significant/stars/method`），仅 SNK 带 `span`
- [x] B7: Kruskal 路径忽略参数事后（tukey/dunnett/lsd/scheffe），退回 Dunn 并说明原因
- [x] B8: 析因方差分析满足 `SS总=SS(A)+SS(B)+SS(AB)+SS误差`，输出标准方差分析表
- [x] B9: 析因交互显著时策略链提示「主效应解释需谨慎」
- [x] B10: 析因不平衡设计用 Type II 平方和，并在策略链说明
- [x] B11: 重复测量满足 `SS总=SS时间+SS受试者+SS误差`，输出时间效应 F/p
- [x] B12: 重复测量数据不平衡（受试者×水平非唯一或缺失）时报可读错误，提示改用混合模型
- [x] B13: 重复测量明确标注「未做球形性校正」，提示违反球形假设时改用 Greenhouse-Geisser
- [x] B14: 两独立均数样本量 d=0.5/0.8/1.0 → 每组约 64/26/17（α=0.05，power=0.8）
- [x] B15: 样本量支持 one_mean / two_means / paired_means / two_proportions / anova / correlation 六种设计
- [x] B16: 样本量支持 `solve=power`（给定 n 反解效能）
- [x] B17: 样本量不依赖数据列，`target_columns` 为空也能通过校验并执行
- [x] B18: `/capabilities` 披露 `factorial_anova`、`repeated_measures_anova`、`sample_size`
- [x] B19: `MethodType` 与注册表键集合保持一致（契约测试守护）
- [x] B20: 审阅卡两两比较表新增 `method` 列可正常渲染

## 验收标准

- [硬门] B1–B20 均有确定性测试，先确认 RED 再最小实现
- [硬门] Tukey 与 `pairwise_tukeyhsd`、Dunnett 与 `scipy.stats.dunnett`、析因与 `anova_lm`、重复测量与 `AnovaRM` 的 p 值在 1e-6 内一致
- [硬门] 析因与重复测量的平方和恒等式在 1e-8 内成立
- [硬门] `pyproject.toml` 的 scipy 下限为 `>=1.14`
- [硬门] 后端 `pytest` 全绿且覆盖率 ≥83%；前端 `vitest`/`build`/`lint` 全绿；E2E 2 项不回归
- [硬门] Kruskal 路径不会调用参数事后（避免用错误差项）
- [软标] `method_note` 能让人看懂「这个方法控制的是哪种错误率、什么时候不该用」

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `significance.tukey_q_pvalue` + `methods.anova` | `test_posthoc.py::test_tukey_matches_pairwise_tukeyhsd` |
| B2 | `methods.anova(correction="dunnett")` | `test_posthoc.py::test_dunnett_matches_scipy` |
| B3 | 同上 | `test_posthoc.py::test_dunnett_requires_control_group` |
| B4 | `methods.anova(correction="lsd")` | `test_posthoc.py::test_lsd_is_uncorrected_t` |
| B5 | 同上 | `test_posthoc.py::test_scheffe_is_more_conservative_than_tukey` |
| B6 | `anova.pairwise.columns` | `test_posthoc.py::test_posthoc_columns_are_uniform` |
| B7 | `anova`（非正态） | `test_posthoc.py::test_kruskal_ignores_parametric_posthoc` |
| B8/B9/B10 | `inference.factorial_anova` | `test_design_anova.py::test_factorial_ss_identity` 等 |
| B11/B12/B13 | `inference.repeated_measures_anova` | `test_design_anova.py::test_repeated_measures_ss_identity` 等 |
| B14/B15/B16/B17 | `inference.sample_size` | `test_sample_size.py` |
| B18 | `GET /capabilities` | `test_capabilities.py` |
| B19 | `MethodType` vs registry | `test_method_contract.py` |
| B20 | `ReviewCard` 渲染 | `ReviewCard.methodNote.test.tsx`（扩展）或既有表格渲染 |

## 依赖与影响

- `pyproject.toml`：`scipy>=1.12` → `>=1.14`（`dunnett` 引入版本）。
- `stats/significance.py`：新增 `tukey_q_pvalue`、`lsd_t_pvalue`、`scheffe_pvalue` 纯函数。
- `stats/methods.py`：`anova` 事后分支扩展；`control_group` 参数；Kruskal 回退。
- `stats/inference.py`：新增 `factorial_anova`、`repeated_measures_anova`、`sample_size`。
- `stats/registry.py`：注册三工具；`correction` choices 扩展；`_NO_TARGET_TOOLS` 豁免。
- `stats/notes.py`：三条新说明，标注外部依据。
- `agents/discussion.py`：`MethodType` 增三个名称。
- 文档：`statistics-methods.md`（公式与来源）、`design-notes.md`（外部标准引入规则）、`timeline.md`、`TO_DO.md`、`CODEBUDDY.md`。

## 备注

- **Tukey 与 SNK 的唯一差别**是 span：SNK 用两组的位次跨度，Tukey 固定用组数 k，因此 Tukey 更保守。
- **Dunnett 需要原始样本**而非均值，直接复用 `anova` 内的 `groups`，避免二次聚合。
- **重复测量球形性**：`AnovaRM` 不做校正，必须在输出 `sphericity_corrected=false` 并在策略链与 `method_note` 明示。
- **样本量工具**是设计期工具：`target_columns` 允许为空，`min_rows=0`，`charts=()`。
- **失败降级**：参数不足抛 `ValueError`，经 `execute_step` 转 `EXECUTION_FAILED`，单步隔离不阻断 pipeline。

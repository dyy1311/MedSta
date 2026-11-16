# MedSta 统计/作图工具登记

> 单一真相源：`backend/src/medsta/stats/registry.py`。本文件由 `tests/test_docs_consistency.py` 守护，
> 新增/修改工具必须同步更新（参数明细以 `GET /capabilities` 实时输出为准，此处登记能力概要）。

## 统计工具（原子单位）

每个工具 = 一个可独立装配的原子统计指令：宿主校验参数 → 执行 → 输出 JSON。
用户在「工具装配」中自行组合为工作链，也可从模型建议导入后修改。

| 工具 | 名称 | 分类 | 任务 | 支持图表 | 适用条件 |
|---|---|---|---|---|---|
| `describe` | 描述性统计 | 描述与质检 | 描述 | histogram / boxplot / violin / pie | 任何分析的第一步：数值/类别列的分布概览，可按分组对比基线特征 |
| `descriptive_stats` | 统计描述（按分布选指标） | 描述与质检 | 描述 | histogram / boxplot / violin | 需要完整描述并判断分布形态时使用：比 describe 多标准差、变异系数、几何均数与 IQR |
| `reference_range` | 医学参考值范围 | 描述与质检 | 描述 | — | 临床参考值范围估计：须明确单双侧与百分数；偏态资料用百分位数法 |
| `one_sample_test` | 单样本检验 | 组间比较 | 关联 | histogram / boxplot | 样本均数与已知总体均数 μ0 比较；需提供 μ0，单双侧须分析前确定 |
| `missing_report` | 缺失数据报告 | 描述与质检 | 描述 | — | 任何数据接入后必做：用于缺失机制判定（MCAR/MAR/MNAR）与数据契约确认 |
| `impute` | 缺失值插补 | 描述与质检 | 描述 | — | 缺失处理：先诊断模式与机制提示，再决定完整病例/MICE/敏感性分析；单数据集插补不等于多重插补 |
| `normality_test` | 正态性检验 | 描述与质检 | 描述 | qq_plot / histogram | 参数/非参数方法选择的前置检验；n<3 或 n>5000 时结论需谨慎 |
| `group_compare` | 两组比较 | 组间比较 | 关联 | boxplot / violin | 两组独立/配对连续样本的均值差异；分组列至少 2 组且每组建议 n≥3 |
| `anova` | 多组比较 | 组间比较 | 关联 | boxplot / grouped_bar / violin | 三组及以上连续样本的组间差异；需分组列且各组建议 n≥3 |
| `randomized_block_anova` | 随机区组方差分析 | 组间比较 | 关联 | boxplot / grouped_bar | 随机区组设计：同一区组内条件相近，需分离区组效应；要求每单元 1 个观测 |
| `chi_square` | 卡方检验 | 组间比较 | 关联 | grouped_bar / heatmap | 两个分类变量的独立性检验；期望频数不足时自动降级 Fisher（2×2） |
| `factorial_anova` | 析因设计方差分析 | 组间比较 | 关联 | grouped_bar / boxplot | 两个分类因素对连续结局的影响：需同时看主效应与交互；交互显著时主效应不可直接解释 |
| `repeated_measures_anova` | 重复测量方差分析 | 组间比较 | 关联 | line / boxplot | 同一对象多个时间点/条件的比较：需长表且每受试者×时间点唯一；未做球形性校正 |
| `mcnemar_test` | 配对四格表 McNemar 检验 | 组间比较 | 关联 | grouped_bar | 配对设计的两个二分类变量比较（同一对象两种方法）；不能当作独立样本卡方 |
| `survival_analysis` | 生存分析 | 组间比较 | 预测 | survival_curve | 随访资料：结局是「事件发生时间」且含删失，不能按普通均值比较处理 |
| `sample_size` | 样本量与检验效能 | 研究设计 | 设计 | — | 研究开始前：给定效应量与目标效能求样本量，或评估现有样本的检验效能；不需要数据 |
| `correlation` | 相关性分析 | 关联与预测 | 关联 | heatmap / scatter | 两个及以上数值列的线性/单调关联强度；不构成因果结论 |
| `regression` | 线性回归 | 关联与预测 | 预测 | residual_plot / scatter | 连续结局的多因素关联与预测；自变量需数值化，样本量≥特征数×10 更稳 |
| `logistic_regression` | Logistic 回归 | 关联与预测 | 预测 | bar / grouped_bar | 二分类结局的风险因素分析（OR/AUC）；结局必须 0/1 且两类均有样本 |
| `timeseries_forecast` | 时间序列预测 | 关联与预测 | 预测 | line | 有序观测的短期趋势外推；需≥3 个有效点，仅适用无强季节性序列 |
| `levene_test` | 方差齐性检验 | 描述与质检 | 描述 | boxplot | 组间比较的前置检验：连续值变量 + 分组列；与正态性检验配合决定最终检验方法 |
| `aggregate_table` | 分组聚合表 | 描述与质检 | 描述 | grouped_bar / pie / bar | 需要汇总报表或为柱状/饼图准备聚合数据时使用；值变量应为数值列 |

## 作图类型

| 图表 | 名称 |
|---|---|
| `histogram` | histogram |
| `boxplot` | boxplot |
| `violin` | violin |
| `scatter` | scatter |
| `line` | line |
| `bar` | bar |
| `grouped_bar` | grouped bar |
| `pie` | pie |
| `heatmap` | heatmap |
| `qq_plot` | Q-Q plot |
| `residual_plot` | residual plot |
| `survival_curve` | survival curve |

## 输出与导出契约

- 所有统计工具输出为 JSON（`tests/test_json_contract.py` 硬门：`json.dumps(allow_nan=False)` 必须通过）。
- 前端一律以表格/图呈现；下载：表格 JSON/CSV/XLSX，图 PNG/JPG/PDF/TIF（`GET /export/{session_id}/{step_index}?format=…&report_id=…`）。


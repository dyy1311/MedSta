# 统计方法映射与能力边界

> 单一真相源：`backend/src/medsta/stats/registry.py` 的 `ToolSpec`（方法、必填槽位、允许图表、适用条件、实现）。
> 方法学依据：项目内《医学统计处理流程图_可复用工作流.html》（八道门禁 G0–G7、四块决策板）与《医学统计前沿方法论_顶刊统计策略图谱.html》（终点类型决策表、十步法、十大前沿打法）。
>
> **图**：策略选择决策树与执行流程见 [系统架构与统计流程](./architecture.md)（图 2、图 3）。
> 本文只写文字口径与依据，不重复画图，避免两处维护。

## 槽位化与依据显式化

- 每个 ToolSpec 声明 `task`（sta_task：描述/关联/因果/预测/决策）、`slots`（group_col/value_col/agg 等语义槽位）、`applicability`（适用条件，进能力抽屉与模型上下文）。
- 模型生成方案必须逐步骤填写 `rationale`（选择依据），缺失即被宿主拒绝（MISSING_PARAM）。
- 检验方法选择由执行期**策略链**确定性完成，每步判定记入 `strategy.steps[]`，最终方法与次优建议可追溯。

## 变量类型推断（020）

四槽位：`continuous`（连续）/ `ordinal`（数值-等级）/ `categorical`（类别）/ `index`（序列索引，统计默认排除）；
内部另有 `datetime` / `boolean` / `text`。

整数列的判定顺序（`data/profiler.py`）：

1. **索引优先**：行数 ≥5、取值唯一且单调、起始 0/1 → `index`；
2. **测量指标白名单**：列名命中常见连续测量（`age`/`height`/`weight`/`bmi`/`bp`/`sbp`/`dbp`/`hr`/`temp`/`glucose`/`creatinine`/`hemoglobin` 等，英文按词元匹配；中文含 年龄/身高/体重/血压/心率/血糖/肌酐/血红蛋白 等）→ `continuous`；
3. **评分/分级**：非负且 `max-min ≤ 10` → `ordinal`（Likert、0–10 评分、分级）；
4. **宽范围整数计数**：其余 → `continuous`；
5. 0/1 整数保持 `ordinal`（既有类型映射契约）。

用户可在画像表逐列修正；类型确认卡提供「数值列全部设为连续」，仅作用于 `continuous`/`ordinal` 列。

## 检验策略链

> 完整决策树（含四条主干与降级路径）见 [架构文档图 2](./architecture.md)。以下为文字版细节与阈值。

### 变量角色：目标列 vs 分组列

每个工具都声明 `accepts`（目标列允许的变量类型）与 `group_param`（分组参数名，如 `group_column`）：

- **类别型/二值列通常是分组或分层变量**（「是否手术」「手术方式」「科室」），应放进 `params.group_column`；
  把它们放进 `target_columns` 会被宿主以 `COLUMN_TYPE_MISMATCH` 拒绝（hint 直接给出「设为分组列」的修法）。
- 若本意是「比较组间率/构成」，正确方法是 `chi_square`（接受类别列），而不是把类别列塞给 t/ANOVA。
- 装配器在勾选目标列时按 `accepts` 实时提示，并提供一键「设为分组列」；讨论模型的 prompt 也禁止
  把类别列放进 `target_columns`（两处约束互为兜底，模型侧只是语义建议，宿主校验才是权威）。

### 连续变量（group_compare / anova）

```
逐组 Shapiro-Wilk 正态性 → Levene 方差齐性 → 组样本量失衡提示（>2:1）
→ 正态+齐性：t / ANOVA
→ 正态+不齐：Welch t（ANOVA 给出谨慎提示）
→ 非正态：Mann-Whitney U / Kruskal-Wallis
→ strategy{steps[], final_method, alternative}
```

分组列 >2 组时拒绝 `group_compare`（避免静默只比较前两组），提示改用 `anova`。

### 分类变量（chi_square）

```
期望频数分析（每格期望、最小期望、期望<5 占比、总样本量）→ 类别 n<5 不平衡提示
→ 占比≤20% 且最小期望≥1：卡方检验
→ 2×2 超出：自动改用 Fisher 精确检验
→ R×C 超出：建议增大样本量或合并相邻类别（不自动执行）
```

### 显著性规范

- α 判定前在"分析配置卡"与用户确认（默认 0.05，可选 0.01/0.001/0.1）。
- 统一星号：`***` p<0.001、`**` p<0.01、`*` p<0.05、ns；`significant` 按用户 α。
- 所有检验结果含 `alpha/significant/stars`；交付表格列含 statistic / p_value / significance。
- 多重比较（≥3 组两两比较）：Holm（默认）/ Bonferroni 校正后 p 值判定显著性，交付卡显示多重性提醒。

## 已实现方法（22 类）

| 方法 | task | 必填槽位 | 图表 |
|---|---|---|---|
| describe | 描述 | —（可选 group_by） | histogram/boxplot/violin/pie |
| descriptive_stats | 描述 | value 列（可选 group_col） | histogram/boxplot/violin |
| reference_range | 描述 | value 列 | 无（表格交付） |
| missing_report | 描述 | —（可选 group_by） | 无 |
| normality_test | 描述 | value 列 | qq_plot/histogram |
| levene_test | 描述 | group_col + value_col | boxplot |
| aggregate_table | 描述 | group_col + value_col + agg | grouped_bar/pie/bar |
| sample_size | 设计 | 无（参数来自研究设计） | 无（结果表） |
| survival_analysis | 预测 | time_col + event_col（可选 group/covariates） | survival_curve |
| impute | 描述 | value 列（可多列） | 无（表格 + 插补数据集） |
| group_compare | 关联 | group_col + value_col | boxplot/violin |
| one_sample_test | 关联 | value 列 + μ0 | histogram/boxplot |
| randomized_block_anova | 关联 | group_col + block_col + value_col | boxplot/grouped_bar |
| factorial_anova | 关联 | factor_a + factor_b + value_col | grouped_bar/boxplot |
| repeated_measures_anova | 关联 | subject_col + within_col + value_col | line/boxplot |
| anova | 关联 | group_col + value_col | boxplot/grouped_bar/violin |
| chi_square | 关联 | row_col + col_col（或 2 个 target） | grouped_bar/heatmap |
| mcnemar_test | 关联 | row_col + col_col（配对二分类） | grouped_bar |
| correlation | 关联 | ≥2 个 value 列 | heatmap/scatter |
| regression | 预测 | value_col(target) + covariates | residual_plot/scatter |
| logistic_regression | 预测 | outcome_col + covariates | bar/grouped_bar |
| timeseries_forecast | 预测 | value 列 | line |

### 教材口径（023）

依据《医学统计学》第 8 版（李康、贺佳）第二、三、十一章：

- **描述指标按分布形态选择**：`classify_distribution` 四态判定（`insufficient`/`normal`/`log_normal`/`skewed`），
  n<3 或取值过少判样本不足；`|偏度|≤1` 且 Shapiro P>α → `x̄±s`；非正态、全为正且对数变换后近似对称 → 几何均数 `G`；
  其余 → `M(P25~P75)`（`descriptive_stats`）。
- **变异指标**：标准差用 n−1 分母（公式 2-12）；`IQR = P75−P25`（2-9）；`CV = S/x̄×100%`（2-15，均数≈0 时不给）。
- **参考值范围**：正态法双侧 `x̄±1.96S`、单侧 `x̄±1.64S`（95%，表 3-1）；百分位数法 `P2.5~P97.5`；
  对数正态法取对数计算后取反对数还原。单双侧由用户按专业知识指定，`auto` 只按分布形态选方法。
  百分位数法 n<100、正态法 n<30 时给稳定性警示。
- **均值差区间**：改用 t 临界值（t 检验用合并方差 df=n1+n2−2，Welch 用 Satterthwaite 自由度，配对用 n−1）；
  非参数路径改报中位数差与 2000 次 bootstrap 区间（固定种子）。
- **配对设计**：正态性检验对象是**差值**；差值非正态降级为 Wilcoxon 符号秩（不是 Mann-Whitney U）。
- **相关**：附 `r_squared` 与强度分档（≤0.3 较差 / 0.3–0.6 中度 / 0.6–0.8 较高 / >0.8 很高），
  并固定提示「相关有统计学意义不等于因果关系」。
- **回归**：输出方差分析表（`SS总=SS回归+SS残差`、MS、F）与残差诊断（Shapiro、Breusch–Pagan、n/k<10 提示）。
- **方法说明**：每种方法的结果附 `method_note`（教材章节与公式、适用条件、解读禁忌），审阅卡可展开查看。

### 第六至十章口径（024）

依据《医学统计学》第 8 版第六至十章：

- **方差齐性（§7）**：两独立样本用 F 检验 `F=S²大/S²小`，**取 α=0.10**；配对设计**不做**方差齐性（教材注意事项 2）。
  多组或非正态资料仍用 Levene（教材 §8 第五节认可），`levene_test` 工具 α 同为 0.10。
- **单样本检验（§7-1、§10-1）**：`t=(x̄−μ0)/(S/√n)`，ν=n−1，附均数 95%CI（t 临界值）；非正态降级 Wilcoxon 符号秩；
  `sides=two/greater/less` 影响 p 与区间单侧界值。
- **随机区组方差分析（§8-3）**：`SS总=SS处理+SS区组+SS误差`，ν误差=(k−1)(b−1)；
  要求每个处理×区组单元恰有 1 个观测，否则报错提示改用两因素方差分析。
- **两两比较（§8-4）**：默认 **SNK-q**，`q=|x̄A−x̄B|/√(MS误差/2·(1/nA+1/nB))`，按跨度用 studentized range 求 p；
  逐步规则——跨度最大的比较不显著时更小跨度不再判显著（原始 p 保留，`step_down` 标记）。
  `correction=holm/bonferroni` 仍可用；SNK 需要 `MS误差`，Kruskal 路径不进入 SNK。
- **Kruskal 事后（§10）**：教材未给公式，采用 **Dunn + Bonferroni**，`method_note` 明确标注来源。
- **四格表三档（§9-1）**：n≥40 且 T≥5 → 专用公式；n≥40 且 1≤T<5 → 校正公式；n<40 或 T<1 → Fisher。
  输出 `tier` 与策略链依据数值；`correction=auto/yes/no`，布尔旧值自动映射。
- **配对四格表（§9-2）**：McNemar `χ²=(b−c)²/(b+c)`，b+c<40 用校正公式；只考察不一致格。
- **多个样本率（§9-3 二）**：整体显著后按 χ² 分割做两两比较，`α'=α/C(k,2)`（`comparison=all_pairs`）
  或 `α/(k−1)`（`vs_control`）；输出的 `alpha_prime` 与 `adjusted_p` 可直接核对。
- **率的区间（§6）**：`group_rates` 给每行率与 95%CI，n≥40 用 Wald、n<40 用 Wilson；`event_value` 指定分子，
  未指定时取列联表第一列并用 `rate_column` 标注。
- **Kendall τ（§11）**：`correlation.method=kendall`，scipy `kendalltau`（τ-b，自动处理 ties），强度分档沿用 023。
- **报告规范（§6 第四节）**：区间与假设检验同等重要，`group_compare`/`one_sample_test`/`rate` 均给区间；
  P 值报告精确值（P<0.001 写法），单双侧须在分析前确定并注明。

### 第十四章 生存分析（027）

依据教材 §14（p.145 起）：

- **KM 乘积极限**（公式 14-4/14-5）：时间升序，**同时间点完全数据排在删失数据之前**；
  `q_i=d_i/n_i`、`p_i=1−q_i`、`S(t_i)=∏p_j`；删失不改变生存率。
- **Greenwood 标准误**（14-6）：`SE=S·√(Σ d_j/(n_j(n_j−d_j)))`；`n_j=d_j` 时该累加项跳过。
- **置信区间**（14-7）：`S±z·SE`；教材指出末端可能越界，实现截断到 [0,1] 并置 `ci_truncated`。
- **中位生存期**：S(t) 首次 ≤0.5 的时间，在相邻时间点间线性插值；若全程 >0.5 返回 `None` 并说明「随访期内生存率未降至 50%」。
- **log-rank**（14-8/14-9）：`χ²=[Σ(d_ki−T_ki)]²/ΣV_ki`；多组用 `g−1` 维二次型（只对第一组求和会让 χ² 偏大）。
- **Breslow**：与 log-rank 的差别仅在权重，`w=n_i`（广义 Wilcoxon），对早期差异更敏感。
- **Cox**（14-11~14-15）：偏似然估计；`HR=exp(β)`，β>0 为危险因素、β<0 为保护因素；
  `PHReg` 的 `llr` 为 `None`，整体 LR 需手建零模型算 `2*(llf_full−llf_null)`。
- **教材未给**：RMST（梯形积分 + Greenwood 方差）、Schoenfeld 残差检验（残差与时间的 Spearman 相关），
  已在 `method_note` 标注为外部标准；**竞争风险 / Fine–Gray 教材 0 处提及**，保持 `planned`。

### 缺失数据（028）

**教材 0 覆盖**：`缺失值 / 插补 / MCAR / MAR / MNAR / 多重插补` 在教材中全部为 0 次，无专章。
依据外部标准：Little & Rubin (2019) 的缺失机制分类、van Buuren (2018) 的 MICE。

- **诊断（`missing_report`）**：逐列缺失率、缺失模式（`none`/`univariate`/`monotonic`/`arbitrary`）、
  完整行比例、分组缺失差异卡方。机制只给 `mechanism_hint`，并固定声明「不能仅凭数据断定 MCAR/MAR/MNAR」。
- **插补（`impute`）**：
  - `mice`（默认）：`IterativeImputer` 跑 m 次（默认 20，上限 50），取逐元素均值写入；
    同时输出 `between_imputation_variance`（m 次插补间的逐元素方差均值）作为不确定性指示。
  - `median`/`mean`/`locf`：仅敏感性分析，标记 `sensitivity_only=true`，不产出数据集。
- **单数据集 ≠ 多重插补**：产出的是 single imputation，不是 Rubin 合并，标准误必然偏小。
  该声明出现在结果字段、`method_note` 与数据集名称三处。
- **数据集产出**：CSV 写入 `_artifact_dir/imputed_step.csv`，由 service 注册为会话内新数据集并推
  `dataset_added` 事件；**不自动切换** active，用户在工作区手动切换。
- **delta 扫描**：对插补值加减 delta，输出三行（−delta / 0 / +delta）的均值与标准差偏移表。
- **拒绝条件**：单列缺失 >50%（建议删列）、有效观测 <2。m<20 给警告仍执行，m>50 截断。

### 估计目标 Estimand（029）

**教材 0 覆盖**：`Estimand / 估计目标 / SAP / 伴发事件` 在教材中全部 0 次。依据 **ICH E9(R1) Addendum (2019)**。

五要素：`population`（目标人群）、`variable`（结局变量）、`treatment`（处理与对照）、
`intercurrent_events`（伴发事件 + 五选一策略：treatment-policy / hypothetical / composite /
while-on-treatment / principal-stratum）、`summary_measure`（群体水平汇总指标）。

- **状态判定归宿主**：`sap_status_of(plan)` 只看四个文本要素是否全非空。
  `intercurrent_events` 允许为空（表示无伴发事件），不参与判定——否则「无伴发事件」会被误标为未声明。
- **两种状态**：`estimand_declared`（已声明估计目标）与 `exploratory`（探索性）。
  **即使五要素齐全也不称 pre-specified 或确证性**：系统无法验证事前注册、盲态与 SAP 冻结。
- **文案红线**：`tests/test_estimand.py` 扫描前后端源码，禁止用 `pre-specified` 或
  描述本系统流程的「确证性」表述。
- **caveat 二选一**：已声明用「已声明估计目标，但未经事前注册、SAP 冻结与样本量论证」；
  未声明用「探索性分析，未声明估计目标」。两条不叠加。
- **模型可留空**：提示词要求「无法确定时留空，禁止编造人群、干预与伴发事件」；留空即探索性，不阻断方案生成。
- **不做**：SAP 摘要导出、事前注册、五要素与数据列的语义校验、前端编辑五要素。

### 教材未给公式的方法（025）

教材只在表 8-9 列出名称、在练习题与设计章节提及设计类型、在第六章给出检验效能概念，
均无公式与例题。以下实现依据外部标准，并在 `method_note` 中标注来源。

| 方法 | 实现口径 | 依据 |
|---|---|---|
| Tukey HSD | `q=diff/√(MSE/2·(1/na+1/nb))`，`p=studentized_range.sf(q, k, df)`，**k 固定为组数**；不等样本量即 Tukey-Kramer | Tukey's range test（Wikipedia） |
| Dunnett | `scipy.stats.dunnett(*experimental, control=..., random_state=固定种子)`，只比较「对照 vs 各试验组」 | Dunnett 1955；scipy ≥1.14 内置（需固定随机源才可复现） |
| LSD-t | `t=diff/√(MSE·(1/na+1/nb))`，`df=N−k`，不校正 | 最小显著差异定义；教材表 8-9 注明只适合两组 |
| Scheffé | `F=diff²/(MSE·(1/na+1/nb)·(k−1))`，`p=F.sf(F, k−1, df)` | 全族比较；p 值恒不小于 Tukey |
| 析因设计 | 平衡：`SS总=SS(A)+SS(B)+SS(AB)+SS误差` 正交分解；不平衡：statsmodels `anova_lm(typ=2)` | Interaction Effect（ScienceDirect topics） |
| 重复测量 | `SS总=SS时间+SS受试者+SS误差`，`F=MS时间/MS误差` | Repeated Measure Analysis（ScienceDirect topics） |
| 样本量 | `TTestIndPower`/`TTestPower`/`NormalIndPower`/`FTestAnovaPower`；两独立均数 `n=2σ²(zα/2+zβ)²/δ²` | statsmodels `stats.power`；d=0.5/0.8/1.0 → 64/26/17 |

事后比较统一输出 `group_a/group_b/mean_diff/statistic/p_value/adjusted_p/significant/stars/method`，
仅 SNK 额外带 `span`。Kruskal 路径会忽略参数事后方法并退回 Dunn，避免使用错误的误差均方。

### 教材口径 vs 软件默认

| 场景 | 教材 | 本项目 | 理由 |
|---|---|---|---|
| 两组方差齐性 | F 检验，α=0.10 | F 检验，α=0.10 | 按教材 |
| 多组方差齐性 | Bartlett（正态）/Levene（非正态） | Levene，α=0.10 | Levene 对方差齐性偏离更稳健，教材亦认可 |
| ANOVA 事后 | SNK-q（EER） | 默认 SNK-q，可选 Holm/Bonferroni（FWER） | 两者控制目标不同，保留选择 |
| Kruskal 事后 | 未给公式 | Dunn + Bonferroni | 通用做法，明确标注 |
| 四格表校正 | 按 n 与 T 三档 | 同上，`correction=auto` 默认自动 | 按教材 |

### Logistic 回归边界（020）

拟合后检测三种情况：未收敛、`max|β| ≥ 15`、OR 或 95%CI 非有限。命中即拒绝执行，
错误信息说明「完全/准完全分离，OR 不可估计」，并建议减少协变量、合并稀疏类别、增大样本，
或改用 Firth 惩罚回归（尚未实现，见规划中）。不向用户下发溢出或天文数字的 OR。

## 交互与交付

- 多工作区：每个上传表格独立工作区，分页切换；讨论/执行作用于激活工作区。
- 出图确认：确认方案后下发 `chart_config`（每步图表类型 + 多图画板 shared/separate + α + 校正方式），用户 `chart_choice` 后执行。
- 可视化交付：表格型结果（聚合表/两两比较/交叉表/相关对/系数表）渲染为表格卡 + CSV/XLSX 导出（`GET /export/...`）。
- 多重提醒：交付卡黄底提示 p 值校正方法与显著性判断依据。

## 规划中（能力披露标注 planned）

| 能力 | 说明 | 缺口 |
|---|---|---|
| 生存分析 | Cox、KM、RMST、Fine–Gray | 需引入 `lifelines` |
| 多重插补 | MICE、tipping point | 需插补链实现 |
| 多重性校正扩展 | Dunnett、层级 gatekeeping | 当前仅 Holm/Bonferroni |
| Firth 惩罚回归 | 分离数据的可估计 OR | 需新增惩罚似然实现 |

# 统计方法映射与能力边界

> 单一真相源：`backend/src/medsta/stats/registry.py` 的 `ToolSpec`（方法、必填槽位、允许图表、适用条件、实现）。
> 方法学依据：项目内《医学统计处理流程图_可复用工作流.html》（八道门禁 G0–G7、四块决策板）与《医学统计前沿方法论_顶刊统计策略图谱.html》（终点类型决策表、十步法、十大前沿打法）。

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

## 已实现方法（12 类）

| 方法 | task | 必填槽位 | 图表 |
|---|---|---|---|
| describe | 描述 | —（可选 group_by） | histogram/boxplot/violin/pie |
| missing_report | 描述 | —（可选 group_by） | 无 |
| normality_test | 描述 | value 列 | qq_plot/histogram |
| levene_test | 描述 | group_col + value_col | boxplot |
| aggregate_table | 描述 | group_col + value_col + agg | grouped_bar/pie/bar |
| group_compare | 关联 | group_col + value_col | boxplot/violin |
| anova | 关联 | group_col + value_col | boxplot/grouped_bar/violin |
| chi_square | 关联 | row_col + col_col（或 2 个 target） | grouped_bar/heatmap |
| correlation | 关联 | ≥2 个 value 列 | heatmap/scatter |
| regression | 预测 | value_col(target) + covariates | residual_plot/scatter |
| logistic_regression | 预测 | outcome_col + covariates | bar/grouped_bar |
| timeseries_forecast | 预测 | value 列 | line |

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

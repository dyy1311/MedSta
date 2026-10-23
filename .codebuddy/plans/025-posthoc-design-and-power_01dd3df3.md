---
name: 025-posthoc-design-and-power
overview: 教材仅列出 Tukey/Dunnett/LSD-t/Scheffé 的名称与适用范围、只在练习题与设计章节提及析因与重复测量、检验效能只有概念无公式；本 spec 依据外部标准（Wikipedia/scipy/statsmodels 文档）补全四类事后比较、析因设计方差分析、重复测量方差分析与样本量/检验效能计算，不新增依赖。
todos:
  - id: spec-scaffold
    content: 用 [skill:tdd] 建 spec 025，提升 scipy 下限并在注册表与枚举中占位
    status: completed
  - id: posthoc-expand
    content: 在 anova 事后扩展 Tukey/Dunnett/LSD/Scheffé，统一输出列与对照组校验
    status: completed
    dependencies:
      - spec-scaffold
  - id: factorial-anova
    content: 实现 factorial_anova：两因素加交互、Type II 平方和、交互显著提示
    status: completed
    dependencies:
      - posthoc-expand
  - id: repeated-measures
    content: 实现 repeated_measures_anova：AnovaRM、平衡校验、球形性未校正提示
    status: completed
    dependencies:
      - factorial-anova
  - id: sample-size
    content: 实现 sample_size 六种设计与双向求解，放宽目标列校验
    status: completed
    dependencies:
      - repeated-measures
  - id: regression-docs
    content: 跑全量测试与构建，同步方法学文档、时间线与待办清单
    status: completed
    dependencies:
      - sample-size
---

## 产品概述

补齐教材只列名称、未给公式的七项推断统计能力：四种事后多重比较（Tukey、Dunnett、LSD-t、Scheffé）、析因设计方差分析、重复测量方差分析、样本量与检验效能计算。目标是让这些方法在工具目录中从「知道名字」变为「可执行、可解释、可追溯」。

## 核心功能

- **事后比较扩展**：方差分析整体显著后，可选 SNK-q（现有默认）、Tukey HSD、Dunnett（多试验组对同一对照）、LSD-t、Scheffé，以及 Holm/Bonferroni。每种方法输出统一样式的两两结果表，并标明所用方法、对照关系与显著性判定依据。
- **Dunnett 对照组**：必须显式指定对照组的组名；未指定时拒绝执行并列出可选组，不静默取第一个组。
- **析因设计方差分析**：两因素（A、B）及 A×B 交互，输出各效应与误差的平方和、自由度、均方、F 值与 P 值，形成标准方差分析表；提示主效应是否可解释（交互显著时应谨慎解读主效应）。
- **重复测量方差分析**：单因素组内设计（同一受试者多个时间点/条件），输出时间效应、受试者间变异与误差的分解；明确提示未做球形性校正，违反球形假设时结论需谨慎。
- **样本量与检验效能**：支持单样本均数、两独立均数、配对均数、两独立率、单因素方差分析、相关六种设计；可在「给定参数求样本量」与「给定样本量求效能」之间双向求解；不需要上传数据列，参数来自研究设计。
- **口径来源标注**：教材未给公式的方法，在方法说明中标注依据来源（外部统计学标准与软件实现），不冒充教材口径。

## 视觉效果

不新增页面。事后比较仍以审阅卡的表格呈现，新增「方法」与「跨度组数」列；析因与重复测量输出标准方差分析表（来源、平方和、自由度、均方、F、P）；样本量工具输出单行结果卡与所用公式说明。所有字段为增量，旧报告仍可正常渲染。

## 边界

- 析因设计仅支持两因素与一阶交互；三因素及以上交互、裂区设计不做。
- 重复测量仅支持单因素组内与平衡数据；混合设计（组间+组内）、球形性校正、缺失数据处理不做，标注为规划中。
- 样本量计算为设计期工具，不读取数据；效应量可由差值/标准差换算，也接受标准化效应量。

## 技术栈

沿用现有栈，仅提升一个依赖下限：

- Python 3.10+ / numpy / pandas
- **scipy >= 1.14**（`scipy.stats.dunnett` 自 1.14 引入，当前环境 1.18.1 已具备；`pyproject.toml` 由 `>=1.12` 提到 `>=1.14`）
- statsmodels >= 0.14（现 0.15.0）：`AnovaRM`、`ols` + `anova_lm`、`statsmodels.stats.power`
- pydantic v2 / pytest；前端无需改动

## 实现方案

### 1. 四种事后比较并入 `anova.correction`，不新建工具

四种方法共用同一次方差分析的 `MS误差` 与 `df误差`，独立成工具会导致重复计算与口径漂移。

`anova` 的 `correction` choices 扩展为 `snk / tukey / dunnett / lsd / scheffe / holm / bonferroni`，默认 `snk`。在 `methods.py` 增加四个纯函数生成行：

| 方法 | 统计量 | p 值 |
| --- | --- | --- |
| Tukey HSD（Tukey-Kramer，允许不等样本量） | `q = | diff | / sqrt(MSE/2·(1/ni+1/nj))` | `studentized_range.sf(q, k, df_error)`，**k 固定为组数** |
| Dunnett | `t_i = (x̄i−x̄0)/sqrt(MSE·(1/ni+1/n0))` | `scipy.stats.dunnett(*samples, control=control_values)` |
| LSD-t | `t = diff / sqrt(MSE·(1/ni+1/nj))` | `2·t.sf( | t | , df_error)`，不校正 |
| Scheffé | `F = diff² / (MSE·(1/ni+1/nj)·(k−1))` | `f.sf(F, k−1, df_error)` |


`dunnett` 需要原始样本而非均值，直接复用 `anova` 里已有的 `groups`；新增参数 `control_group`（组名），缺失时抛 `ValueError` 并列出全部组名。

统一输出列：`group_a / group_b / mean_diff / statistic / p_value / adjusted_p / significant / stars / method`；仅 `snk` 额外带 `span`，`dunnett` 只产出「对照 vs 各试验组」的行。`pairwise.method` 写入实际所用方法，`multiplicity_warning` 按方法给出不同文案（Scheffé 最保守、LSD 仅适合预设对、Dunnett 仅用于多组对一对照）。

### 2. `factorial_anova`（新工具）

- 参数：`factor_a`（column）、`factor_b`（column）、`interaction`（boolean，默认 true）
- 实现：`statsmodels.formula.api.ols` + `anova_lm(typ=2)`（不平衡设计下 Type II 平方和更稳健），或手写 SS 分解；输出 `source/ss/df/ms/f/p_value` 表，来源含 A、B、A×B、误差、总
- 校验：两因素水平数均 ≥2；每个单元格至少 1 个观测；不完整单元格给可读错误
- 策略链：`SS总=SS(A)+SS(B)+SS(AB)+SS误差`；交互显著时提示主效应解释需谨慎

### 3. `repeated_measures_anova`（新工具）

- 参数：`subject_column`（受试者 ID）、`within_column`（时间/条件）
- 实现：`statsmodels.stats.anova.AnovaRM(data, depvar=值列, subject=受试者, within=[时间]).fit()`
- 输出：`source/ss/df/ms/f/p_value`（时间、误差），附受试者间平方和与 `sphericity_corrected=false`
- 校验：每个受试者×每个水平恰有 1 个观测；不平衡时提示改用混合模型
- 策略链与 `method_note` 必须写明「未做球形性校正，违反球形假设（Mauchly 检验）时应改用 Greenhouse-Geisser 或混合模型」

### 4. `sample_size`（新工具，设计期）

- 参数：`design`（choice：`one_mean/two_means/paired_means/two_proportions/anova/correlation`）、`solve`（choice：`n/power`）、`effect_size`（number，可空）、`delta`、`sigma`、`ratio`、`k_groups`、`alpha`、`power`、`n`
- 实现：
- `two_means` → `TTestIndPower.solve_power`；`one_mean`/`paired_means` → `TTestPower`
- `two_proportions` → `NormalIndPower`，效应量为 Cohen's h，也可由 p1/p2 换算
- `anova` → `FTestAnovaPower`（Cohen's f）
- `correlation` → `NormalIndPower`，效应量 `0.5·ln((1+r)/(1−r))`
- 未给 `effect_size` 时由 `delta/sigma` 换算；两者都缺时抛错并给出提示
- 返回：`design / solve / n_per_group / total_n / power / alpha / effect_size / formula / method_note`
- **校验豁免**：`validate_step` 增加 `_NO_TARGET_TOOLS = {"sample_size"}`，跳过「至少一个目标列」的强制检查；`_SLOT_META` 为空，`charts=()`，`min_rows=0`
- 图表：无，交付为结果表

### 5. 契约同步

新增两个方法与一个设计期工具必须同步：`MethodType`、`_REGISTRY`、`_TASK_META`、`_SLOT_META`、`METHOD_NOTES`、`agents/interpretation.py::_SIMPLE_KEYS`；`test_method_contract.py` 会自动守护枚举一致性。

## 实施要点

- **数值口径**：Tukey 的 k 固定为组数（区别于 SNK 的动态 span）；Scheffé 的 p 值应恒 ≥ Tukey；Dunnett 的 p 值应介于未校正 t 与 Bonferroni 之间，这三条性质直接作为测试断言。
- **Dunnett 调用细节**：`scipy.stats.dunnett(*experimental, control=control)` 的样本顺序必须与输出行顺序一致；组少于 2 个时直接拒绝。
- **Kruskal 路径不进入参数事后**：`test == "kruskal"` 时忽略 `tukey/dunnett/lsd/scheffe`，退回 Dunn，并在 `multiplicity_warning` 说明原因，避免用错误的误差项算 q。
- **重复测量数据整形**：`AnovaRM` 要求平衡长表；先用 `pivot_table` 检查唯一性，再喂入，避免 `AnovaRM` 抛内部异常。
- **性能**：事后比较复杂度 O(k²)，k 通常 <10；`sample_size` 的 `solve_power` 为迭代求根，单次数十毫秒，无瓶颈。
- **失败降级**：所有新方法在参数不足时抛 `ValueError`（经 `execute_step` 转为 `EXECUTION_FAILED`，单步隔离不阻断整条 pipeline）。
- **依赖下限**：`pyproject.toml` 的 scipy 提到 `>=1.14`，否则新环境安装后 `scipy.stats.dunnett` 不存在，会在运行时才暴露。
- **文档**：`statistics-methods.md` 增加七项方法的公式与来源；`design-notes.md` 记录「教材未给公式时如何引入外部标准」；`timeline.md`、`TO_DO.md`、`CODEBUDDY.md` 同步。

## 架构设计

改动集中在统计层与注册表，编排层与前端零改动：

- `methods.py` 负责把 ANOVA 的误差项分发给四种事后比较；
- `inference.py` 承载两个新设计类方法（与 `randomized_block_anova` 同构）；
- `significance.py` 保持统计量与 p 值纯函数；
- `registry.py` 只做注册与校验豁免；
- 前端沿用通用表格渲染，`anova.pairwise` 新增 `method` 列不影响既有渲染。

## 目录结构

```
backend/
├── pyproject.toml                       # [MODIFY] scipy 下限 >=1.12 → >=1.14（dunnett 引入版本）
├── src/medsta/stats/
│   ├── methods.py                       # [MODIFY] anova 事后扩到 7 种：新增 _tukey_rows/_dunnett_rows/
│   │                                    #   _lsd_rows/_scheffe_rows；control_group 参数；Kruskal 路径回退 Dunn；
│   │                                    #   pairwise 统一列与 method 字段；multiplicity_warning 分方法文案
│   ├── significance.py                  # [MODIFY] 新增 tukey_q_pvalue（k 固定）、scheffe_pvalue、
│   │                                    #   lsd_t_pvalue 三个纯函数，便于单测与复用
│   ├── inference.py                     # [MODIFY] 新增 factorial_anova（两因素 + 交互，anova_lm typ=2）、
│   │                                    #   repeated_measures_anova（AnovaRM，含球形性未校正提示）、
│   │                                    #   sample_size（六种设计 × 双向求解，statsmodels.stats.power）
│   ├── registry.py                      # [MODIFY] 注册 3 个工具；anova.correction 扩展 choices 与
│   │                                    #   control_group 参数；_NO_TARGET_TOOLS 豁免 sample_size
│   └── notes.py                         # [MODIFY] 新增 3 条 method_note，标注「教材仅列表，公式依据外部标准」
├── src/medsta/agents/
│   └── discussion.py                    # [MODIFY] MethodType 增 factorial_anova / repeated_measures_anova / sample_size
└── tests/
    ├── test_posthoc.py                  # [NEW] Tukey/Dunnett/LSD/Scheffé：与 pairwise_tukeyhsd、scipy.dunnett
    │                                    #   对齐；Scheffé ≥ Tukey；Dunnett 介于未校正与 Bonferroni；control_group 校验
    ├── test_design_anova.py             # [NEW] 析因（SS 恒等式、交互、不平衡 typ=2）、重复测量（SS 恒等式、
    │                                    #   不平衡报错、球形性提示）
    ├── test_sample_size.py              # [NEW] 六种设计 × solve=n/power；d=0.5/0.8/1.0 → 64/26/17；
    │                                    #   缺 effect_size 与 delta/sigma 时报错
    └── test_stats_methods.py            # [MODIFY] anova.pairwise 列变更同步（新增 method/span）
docs/
├── statistics-methods.md                # [MODIFY] 七项方法公式、来源与适用条件对照表
├── design-notes.md                      # [MODIFY] 新增一节：教材未给公式时的外部标准引入规则
├── timeline.md / TO_DO.md / CODEBUDDY.md# [MODIFY] 记录 025 与已知限制更新
spec/done/                               # [NEW] 025-posthoc-design-and-power.md
```

## 关键接口

```python
def tukey_q_pvalue(mean_a, mean_b, n_a, n_b, ms_error, df_error, groups: int) -> tuple[float, float]
def scheffe_pvalue(mean_a, mean_b, n_a, n_b, ms_error, df_error, groups: int) -> tuple[float, float]
def factorial_anova(df, step, params) -> dict      # params: factor_a, factor_b, interaction
def repeated_measures_anova(df, step, params) -> dict  # params: subject_column, within_column
def sample_size(df, step, params) -> dict          # params: design, solve, effect_size/delta/sigma, alpha, power, n
```

## 测试策略

教材无例题，采用三层基准：

1. **与成熟实现对齐**：Tukey 对 `statsmodels.stats.multicomp.pairwise_tukeyhsd`；Dunnett 对 `scipy.stats.dunnett`；析因对 `statsmodels.anova_lm`；重复测量对 `AnovaRM`。
2. **恒等式与序关系**：`SS总=SS(A)+SS(B)+SS(AB)+SS误差`；`SS总=SS时间+SS受试者+SS误差`；Scheffé p ≥ Tukey p；Dunnett p 介于未校正与 Bonferroni 之间。
3. **公开速查值**：两独立均数 d=0.5/0.8/1.0 → 每组 64/26/17（α=0.05、power=0.8）。

## Agent Extensions

### Skill

- **tdd**
- Purpose: 项目强制 spec 驱动 + TDD，按「一条行为 → 一个测试先 RED → 最小实现 GREEN」推进。
- Expected outcome: 每条行为有 RED→GREEN 记录；四种事后比较与三种设计类方法均有确定性基准；新增用例不拉低 83% 覆盖率门槛。
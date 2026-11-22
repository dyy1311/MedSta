# 045 数据清洗层

## 背景

TO_DO P1「数据清洗层」：上传数据在分析前常需去重、筛异常、变换。
现有工具族（22 个）缺预处理能力，用户只能在分析中「硬扛」脏数据。
本 spec 新增 6 个零模型确定性清洗工具，遵循 028 impute 的数据产出型约定
（写 `cleaned_step_{i}.csv` + `_next_frame` 链间管道 + service 注册新数据集）。

## 工具与行为列表（每条可测）

### 1. `dedupe`（去重）

- B1 整行去重（target_columns/params.columns 为空时）：`keep=first` 默认；产出
  `cleaned_step_{i}.csv`、`cleaned_dataset` payload 与 `_next_frame`；
  table 汇总 n_before/duplicates/n_after。
- B2 `keep=last` 保留最后一次出现；`columns` 指定判重子集列。
- B3 无重复行时不落盘、不产 `_next_frame`，`no_change=true`。

### 2. `filter_rows`（筛选子集）

- B4 `conditions=[{column, op, value}]`，op ∈ eq/ne/gt/ge/lt/le/between/in/isna/notna，
  多条件 AND；产出清洗数据集与 `_next_frame`；table 汇总条件/n_before/n_kept/n_dropped。
- B5 筛后 0 行抛 ValueError（下游统计必然失败，显式拒绝优于静默空表）。
- B6 条件引用不存在的列 / 未知操作符 → ValueError。

### 3. `standardize`（标准化）

- B7 `method=zscore`：列内 (x−mean)/sd（ddof=1），变换后 mean≈0、sd≈1；
  产出清洗数据集与 `_next_frame`。
- B8 `method=minmax`：(x−min)/(max−min)。
- B9 sd=0 / 极差=0 / 有效值<2 / 列含非数值 → ValueError。

### 4. `bin_column`（分箱）

- B10 `method=quantile`（默认）等频分箱，`bins` 默认 4；输出列 `{col}_bin`，
  整数箱号 1..k（NaN 保持缺失）；产出清洗数据集与 `_next_frame`。
- B11 `method=equal_width` 等宽分箱。
- B12 `output_column` 仅在单目标列时生效；分箱数 <2 或有效值不足 → ValueError。

### 5. `outlier_report`（异常值识别，报告型不产数据集）

- B13 `method=iqr`（默认，k=1.5）：P25−k·IQR ~ P75+k·IQR 界外计数；
  `k` 可调。
- B14 `method=zscore`：|z|>3（教材口径）界外计数。
- B15 table 逐列 method/lower/upper/outliers/percent；无 cleaned_dataset、无 _next_frame。

### 6. `winsorize`（截尾）

- B16 `method=iqr`（默认，k=1.5）截到界内；`method=percentile` 按
  lower_pct/upper_pct（默认 1/99）截；产出清洗数据集与 `_next_frame`；
  table 逐列 n_capped_lower/n_capped_upper。

### 注册与契约

- B17 六工具入注册表（category「数据清洗」）；dedupe/filter_rows 允许空
  target_columns（_NO_TARGET_TOOLS）；standardize/bin_column/outlier_report/
  winsorize 的目标列 accepts=("continuous",)。
- B18 MethodType 枚举同步六名（test_method_contract 守护）。
- B19 service 注册 `cleaned_dataset` 产物（dataset_added，`imputed=false`）；
  dedupe→describe 链间管道生效（_next_frame）。
- B20 附录 A（B1）/tools.md（B7）/product-guide（B4）同步六工具。

## 验收标准

- 硬门（确定性测试）：B1–B19 全部由 `tests/test_cleaning.py` 与既有契约测试
  （test_method_contract / test_docs_consistency / test_json_contract）覆盖；
  出口 JSON 严格（allow_nan=False 硬门沿用）。
- 软标：工具 description 与 statistics-methods 口径一致；装配器（ChainBuilder）
  中 conditions 参数的表单体验为后续打磨项（本批仅保证 WS 通道可用）。

## 测试映射

| 行为 | 测试 |
|---|---|
| B1–B3 | test_cleaning.py::test_dedupe_* |
| B4–B6 | test_cleaning.py::test_filter_rows_* |
| B7–B9 | test_cleaning.py::test_standardize_* |
| B10–B12 | test_cleaning.py::test_bin_column_* |
| B13–B15 | test_cleaning.py::test_outlier_report_* |
| B16 | test_cleaning.py::test_winsorize_* |
| B17 | test_method_contract + test_cleaning.py::test_registry_accepts_cleaning_tools |
| B18 | test_method_contract |
| B19 | test_cleaning.py::test_cleaned_dataset_registered_flow / test_chaining_dedupe_then_describe |
| B20 | test_docs_consistency（B1/B4/B7 既有断言） |

## 模型输出契约声明

本批零模型参与：清洗工具为确定性宿主计算，模型仅在讨论态经工具目录引用其名
（MethodType 枚举自动进目录）；无新增 ModelRequest 契约。

# 002 - 数据解析与画像

> 状态：done
> 完成日期：2026-10-17
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

产品工作流第一步：用户上传 CSV/Excel 后，系统解析数据并生成统计画像（类型、缺失值、数值摘要），供讨论智能体在方案设计时使用（只带画像摘要，不带全量数据）。

## 范围

- 做：CSV 与 Excel（xlsx）解析；列类型推断（numeric / categorical / datetime / text / boolean）；每列缺失统计；数值列描述统计（count/mean/std/min/quantiles/max）；整体画像摘要（行数、列数、列画像列表）；画像 JSON 序列化（pydantic 模型，可入库可下发）。
- 不做：数据清洗改写、上传接口（在 005 会话 API 中做）、大数据分块加载（轻量原则：一次性读入）。

## 行为列表（TDD 循环队列）

- [x] B1: 解析 UTF-8 CSV（含数值列、类别列、缺失单元格），返回 DataFrame 且行数正确
- [x] B2: 数值列画像：类型 numeric，含 count/mean/std/min/50%/max 且缺失数正确
- [x] B3: 类别列画像：类型 categorical，含 distinct 计数与最高频类别
- [x] B4: 画像汇总：包含 row_count、column_count 与逐列画像；整体可 `model_dump_json` 序列化
- [x] B5: 解析 xlsx 文件与 CSV 等价数据得到一致画像
- [x] B6: 不支持的文件扩展名抛出带说明的 ValueError

## 验收标准

- [硬门] B1–B6 由 pytest 走公共接口（`load_table` / `profile_dataframe`）验证 GREEN
- [硬门] 画像模型字段可 JSON 序列化（无 numpy 类型泄漏）
- [软标] 类型推断对整数+缺失、小数、布尔、日期字符串给出合理分类

## 契约与测试映射

公共接口：`medsta.data.parser.load_table(path) -> DataFrame`；`medsta.data.profiler.profile_dataframe(df) -> TableProfile`。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `load_table` | `tests/test_parser.py::test_load_csv` |
| B2 | `profile_dataframe` | `tests/test_profiler.py::test_numeric_column_profile` |
| B3 | `profile_dataframe` | `tests/test_profiler.py::test_categorical_column_profile` |
| B4 | `profile_dataframe` | `tests/test_profiler.py::test_table_profile_summary_and_json` |
| B5 | `load_table` | `tests/test_parser.py::test_load_xlsx` |
| B6 | `load_table` | `tests/test_parser.py::test_unsupported_extension` |

## 依赖与影响

- 依赖 001 的包骨架。产出的 `TableProfile` 是 003 讨论智能体 prompt 的 `info` 输入。

## 备注

- 数值列缺 std 的单值列：std 记为 null（可空字段）。

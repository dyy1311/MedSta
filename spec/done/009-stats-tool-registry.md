# 009 - 统计工具库（参数契约 + 10 类方法 + 图表）

> 状态：done
> 创建：2026-10-18 ｜ 敲定：2026-10-18 ｜ 完成：2026-10-18

## 背景与目标

线上报错 `executor.py:147 KeyError: 'group_column'`：`hypothesis_test` 直接取参数，而模型从未被告知该参数必填——"特征槽位"与"统计脚本"缺少共享契约。本 spec 建立单一真相源 `ToolSpec`（方法名、必填参数、允许图表、实现），宿主动态校验，模型只做选择；同时按《医学统计处理流程图》《顶刊统计策略图谱》的终点类型决策表补齐方法覆盖，修复图表中文缺字。

## 范围

- 做：`stats/registry.py` 契约与校验；10 类方法（describe/missing_report/normality_test/group_compare/anova/chi_square/correlation/regression/logistic_regression/timeseries_forecast）；10 类图表；中文字体配置与英文回退；executor 改为注册表派发 + 逐步错误捕获（failed 而非整体崩溃）。
- 不做：生存分析（Cox/Fine-Gray/RMST，需 lifelines）、多重插补（MICE）、多重性校正（后续 spec）、模型侧 options/流式（010/011）。

## 行为列表（TDD 循环队列）

- [x] B1: `tool_catalog()` 含 10 个方法，每项含 name/title/category/params/charts
- [x] B2: 缺必填参数（group_compare 无 group_column）返回 `MISSING_PARAM` issue，不抛 KeyError
- [x] B3: 引用不存在列返回 `COLUMN_NOT_FOUND`；未知方法返回 `TOOL_NOT_FOUND`
- [x] B4: 非法取值（test=not_a_test）返回 `INVALID_PARAM`
- [x] B5: describe 支持分组，输出每列 n/mean/sd/median
- [x] B6: group_compare 输出 test/statistic/p/cohens_d，且生成图表
- [x] B7: anova 输出统计量/p/eta_squared；组数 <2 返回 INSUFFICIENT_DATA
- [x] B8: chi_square 2×2 输出 OR 与 Cramér's V
- [x] B9: logistic_regression 输出 OR 与 accuracy
- [x] B10: missing_report 输出逐列缺失数与比例
- [x] B11: normality_test 输出 W/p/is_normal
- [x] B12: correlation 支持 pearson/spearman 与 p 值
- [x] B13: regression 输出系数 95%CI 与 p 值
- [x] B14: timeseries_forecast 输出 forecast_values 长度 = forecast_n
- [x] B15: 中文标题图表不产生 "Glyph ... missing" 警告
- [x] B16: executor 单步异常记为 failed（含 error.code），不中断其余步骤；未知方法抛 ToolValidationError(ValueError)

## 验收标准

- [硬门] B1–B16 pytest 全绿，既有 45 项不回归
- [硬门] 缺参/列不存在错误含 code/message/hint
- [软标] 图表标题中文可读（有 CJK 字体时）

## 契约与测试映射

| 行为 | 公共接口 | 测试 |
|---|---|---|
| B1–B4 | `medsta.stats.registry.validate_step/tool_catalog` | `tests/test_stats_registry.py` |
| B5–B14 | `registry.execute_step` | `tests/test_stats_registry.py` |
| B15 | `stats.plotting.render_chart` | `tests/test_stats_registry.py::test_chart_no_missing_glyph_warning` |
| B16 | `PipelineExecutor.execute` | `tests/test_pipeline.py` |

## 依赖与影响

- 修改 `executor.py`（派发与错误捕获）、`agents/discussion.py` 的 MethodType（改为注册表校验，见 010 前置）。`ExecutionReport` 兼容扩展 `error` 字段。

## 备注

- `hypothesis_test` 保留为 `group_compare` 的兼容别名（既有测试与历史记录）。
- 中文字体优先 Noto Serif CJK SC（已确认系统存在），无 CJK 时标题回退英文，避免乱码与警告刷屏。

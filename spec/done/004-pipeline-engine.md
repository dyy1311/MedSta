# 004 - Pipeline 执行引擎与 Artifact 产出

> 状态：done
> 完成日期：2026-10-17
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

执行态核心：方案确认后，`PipelineExecutor` 按 `AnalysisPlan.steps` 顺序确定性执行（宿主代码，无模型参与），产出结果数据与图表 artifact 文件，并汇总为 `ExecutionReport`。步骤执行是纯确定性计算，可测试、可复现。

## 范围

- 做：步骤执行器——`describe`（数值列描述统计）、`correlation`（数值列相关矩阵）、`regression`（OLS：因变量+自变量）、`timeseries_forecast`（线性趋势外推 forecast_n 步）、`hypothesis_test`（两独立样本 t 检验）；绘图——histogram/boxplot/scatter/line/bar/heatmap/none，matplotlib 后端 Agg 输出 PNG artifact；`ExecutionReport`（逐步骤结果 + artifact 路径，可 JSON 序列化）；`PipelineExecutor.execute(df, plan, artifact_dir)` 公共接口。
- 不做：TriggerFlow 应用层编排（005 会话 API 中接线）；模型调用（执行态无模型）；高级模型诊断。

## 行为列表（TDD 循环队列）

- [x] B1: describe 步骤对数值列产出描述统计结果（JSON 兼容 dict）
- [x] B2: histogram 步骤产出 PNG artifact 文件且结果含 artifact 路径
- [x] B3: correlation 步骤产出列间相关系数结果
- [x] B4: timeseries_forecast 步骤按 params.forecast_n 产出预测值序列
- [x] B5: regression 步骤（params.target + params.features）产出系数与 R²
- [x] B6: hypothesis_test 步骤产出 t 统计量与 p 值
- [x] B7: 多步骤 plan 顺序执行，ExecutionReport 含全部步骤且状态为 success
- [x] B8: 未知 method 抛出带说明的 ValueError（执行器拒绝契约外方法；实施备注：pydantic 契约先行拦截，执行器守卫为纵深防御，测试用 model_construct 绕过契约层）

## 验收标准

- [硬门] B1–B8 pytest 走公共接口 GREEN；artifact 落盘在 tmp_path；结果可 JSON 序列化
- [硬门] matplotlib 使用 Agg 后端，不弹窗、不依赖显示环境

## 契约与测试映射

公共接口：`medsta.pipeline.executor.PipelineExecutor.execute(df, plan, artifact_dir) -> ExecutionReport`。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `execute` | `tests/test_pipeline.py::test_describe_step` |
| B2 | `execute` | `tests/test_pipeline.py::test_histogram_artifact` |
| B3 | `execute` | `tests/test_pipeline.py::test_correlation_step` |
| B4 | `execute` | `tests/test_pipeline.py::test_forecast_step` |
| B5 | `execute` | `tests/test_pipeline.py::test_regression_step` |
| B6 | `execute` | `tests/test_pipeline.py::test_hypothesis_test_step` |
| B7 | `execute` | `tests/test_pipeline.py::test_multi_step_report` |
| B8 | `execute` | `tests/test_pipeline.py::test_unknown_method_rejected` |

## 依赖与影响

- 依赖 003 的 AnalysisPlan。ExecutionReport 与 artifact 路径被 005 会话编排与前端消费。

## 备注

- 预测采用轻量线性趋势（numpy polyfit）；后续如需 ARIMA 在新 spec 中扩展。

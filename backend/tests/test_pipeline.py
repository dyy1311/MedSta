"""004 pipeline 执行器：execute 公共接口测试。"""
import pandas as pd
import pytest

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.pipeline.executor import ExecutionReport, PipelineExecutor


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month_num": [1, 2, 3, 4, 5, 6],
            "sales": [120.0, 135.5, 128.0, 150.0, 158.0, 171.2],
            "region": ["east", "west", "east", "east", "west", "east"],
        }
    )


def _plan(steps: list[PlanStep]) -> AnalysisPlan:
    return AnalysisPlan(message="测试方案", steps=steps)


def test_describe_step(tmp_path) -> None:
    """B1: describe 步骤对数值列产出描述统计结果"""
    step = PlanStep(
        title="销量描述统计",
        method="describe",
        target_columns=["sales"],
        chart_type="none",
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    assert isinstance(report, ExecutionReport)
    assert report.steps[0].status == "success"
    stats = report.steps[0].result["stats"]["sales"]
    assert abs(stats["mean"] - 143.7833) < 0.01
    assert stats["count"] == 6


def test_histogram_artifact(tmp_path) -> None:
    """B2: histogram 步骤产出 PNG artifact 且结果含 artifact 路径"""
    step = PlanStep(
        title="销量分布图",
        method="describe",
        target_columns=["sales"],
        chart_type="histogram",
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    artifact = tmp_path / report.steps[0].result["artifact"]
    assert artifact.exists() and artifact.stat().st_size > 0
    assert artifact.suffix == ".png"


def test_correlation_step(tmp_path) -> None:
    """B3: correlation 步骤产出列间相关系数"""
    step = PlanStep(
        title="相关性",
        method="correlation",
        target_columns=["month_num", "sales"],
        chart_type="heatmap",
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    corr = report.steps[0].result["correlation"]["sales"]["month_num"]
    assert corr > 0.95  # 销量随月份近似线性增长


def test_forecast_step(tmp_path) -> None:
    """B4: timeseries_forecast 按 params.forecast_n 产出预测值"""
    step = PlanStep(
        title="销量预测",
        method="timeseries_forecast",
        target_columns=["sales"],
        chart_type="line",
        params={"forecast_n": 3},
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    result = report.steps[0].result
    assert len(result["forecast_values"]) == 3
    # 线性趋势外推：最后一个预测值应大于历史最大值（上升趋势）
    assert result["forecast_values"][-1] > _df()["sales"].max()


def test_regression_step(tmp_path) -> None:
    """B5: regression 产出系数与 R²"""
    step = PlanStep(
        title="回归",
        method="regression",
        target_columns=["sales", "month_num"],
        chart_type="scatter",
        params={"target": "sales", "features": ["month_num"]},
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    result = report.steps[0].result
    assert result["r_squared"] > 0.9
    assert "month_num" in result["coefficients"]


def test_hypothesis_test_step(tmp_path) -> None:
    """B6: hypothesis_test 产出 t 统计量与 p 值"""
    step = PlanStep(
        title="区域差异检验",
        method="hypothesis_test",
        target_columns=["sales"],
        chart_type="boxplot",
        params={"group_column": "region"},
    rationale="测试依据：数值列与任务匹配", )
    report = PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)
    result = report.steps[0].result
    assert "statistic" in result and "p_value" in result and "strategy" in result


def test_multi_step_report(tmp_path) -> None:
    """B7: 多步骤顺序执行，报告含全部步骤且全为 success"""
    plan = _plan(
        [
            PlanStep(title="统计", method="describe", target_columns=["sales"], chart_type="none", rationale="测试依据：数值列与任务匹配", ),
            PlanStep(title="分布图", method="describe", target_columns=["sales"], chart_type="histogram", rationale="测试依据：数值列与任务匹配", ),
        ]
    )
    report = PipelineExecutor().execute(_df(), plan, artifact_dir=tmp_path)
    assert len(report.steps) == 2
    assert report.all_success
    assert report.model_dump_json()  # 可 JSON 序列化


def test_unknown_method_rejected(tmp_path) -> None:
    """B8: 未知 method 抛出带说明的 ValueError（绕过 pydantic 契约，测执行器纵深防御）"""
    step = PlanStep.model_construct(
        title="未知方法",
        method="magic",
        target_columns=["sales"],
        chart_type="none",
        params={},
    rationale="测试依据：数值列与任务匹配", )
    with pytest.raises(ValueError, match="magic"):
        PipelineExecutor().execute(_df(), _plan([step]), artifact_dir=tmp_path)


def test_step_failure_isolated(tmp_path) -> None:
    """B16(009): 单步运行期异常记为 failed 且不拖垮后续步骤"""
    bad = PlanStep(
        title="非法回归",
        method="regression",
        target_columns=["sales"],
        chart_type="none",
        params={"target": "sales", "features": ["region"]},
    rationale="测试依据：数值列与任务匹配", )
    good = PlanStep(
        title="销量描述", method="describe", target_columns=["sales"], chart_type="none",
        rationale="测试依据：数值列与任务匹配",
    )
    report = PipelineExecutor().execute(_df(), _plan([bad, good]), artifact_dir=tmp_path)
    assert report.steps[0].status == "failed"
    assert report.steps[0].error["code"] == "EXECUTION_FAILED"
    assert report.steps[1].status == "success"

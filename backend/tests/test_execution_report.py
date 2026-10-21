"""019 B13：执行报告结构、artifact 契约、失败隔离与进度回调。"""
from __future__ import annotations

import json
import pathlib

import pandas as pd

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.pipeline.executor import PipelineExecutor


DF = pd.DataFrame(
    {
        "group": ["A", "A", "A", "B", "B", "B"],
        "value": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        "age": [20, 21, 22, 41, 42, 43],
    }
)


def _step(title: str, method: str, targets: list[str], chart: str = "none", **params) -> PlanStep:
    return PlanStep(
        title=title,
        method=method,
        target_columns=targets,
        chart_type=chart,
        params=params,
        rationale="报告契约测试依据",
    )


def _plan(*steps: PlanStep) -> AnalysisPlan:
    return AnalysisPlan(message="报告测试", steps=list(steps))


def test_report_preserves_order_and_table_contract(tmp_path) -> None:
    """B13: 报告按计划顺序记录，表格步骤带 columns/rows，artifact 是文件名。"""
    plan = _plan(
        _step("描述统计", "describe", ["value"], chart="histogram"),
        _step("两组比较", "group_compare", ["value"], chart="boxplot", group_column="group"),
    )

    report = PipelineExecutor().execute(DF, plan, artifact_dir=tmp_path)

    assert [step.title for step in report.steps] == ["描述统计", "两组比较"]
    assert [step.method for step in report.steps] == ["describe", "group_compare"]
    assert report.all_success

    describe = report.steps[0]
    assert describe.table is not None
    assert describe.table["columns"][0] == "column"
    assert describe.artifact == "step_0_describe_histogram.png"

    compare = report.steps[1]
    assert compare.table is not None
    assert {"test", "statistic", "p_value", "significance"} <= set(compare.table["columns"])
    assert (pathlib.Path(tmp_path) / compare.artifact).is_file()


def test_report_json_is_serializable_without_numpy_types(tmp_path) -> None:
    """B13: 报告可直接经 WS 下发（numpy 标量/NaN 已被转换）。"""
    report = PipelineExecutor().execute(
        DF, _plan(_step("描述", "describe", ["value"])), artifact_dir=tmp_path
    )

    payload = json.loads(report.model_dump_json())

    assert payload["steps"][0]["result"]["stats"]["value"]["mean"] == 4.0
    assert isinstance(payload["steps"][0]["result"]["stats"]["value"]["count"], int)


def test_failure_is_isolated_and_error_is_classified(tmp_path) -> None:
    """B13: 单步运行期失败不拖垮整份报告，失败步骤带 code/message/hint。"""
    plan = _plan(
        _step("非法回归", "regression", ["value"], target="value", features=["group"]),
        _step("正常描述", "describe", ["value"]),
    )

    report = PipelineExecutor().execute(DF, plan, artifact_dir=tmp_path)

    assert report.steps[0].status == "failed"
    assert report.steps[0].error is not None
    assert report.steps[0].error["code"] == "EXECUTION_FAILED"
    assert report.steps[0].error["hint"]
    assert report.steps[0].artifact is None
    assert report.steps[1].status == "success"
    assert report.all_success is False


def test_shared_layout_merges_charts_into_one_artifact(tmp_path) -> None:
    """B13: 两个步骤要求同一画板 → 都指向 charts_combined.png。"""
    plan = _plan(
        _step("分布", "describe", ["value"], chart="histogram", _layout="shared"),
        _step("组间", "group_compare", ["value"], chart="boxplot", group_column="group", _layout="shared"),
    )

    report = PipelineExecutor().execute(DF, plan, artifact_dir=tmp_path)

    assert report.steps[0].artifact == "charts_combined.png"
    assert report.steps[1].artifact == "charts_combined.png"
    assert (pathlib.Path(tmp_path) / "charts_combined.png").is_file()
    assert report.steps[0].result["artifact"] == "charts_combined.png"


def test_progress_callback_reports_every_step(tmp_path) -> None:
    """B13: on_step 回调按 (index,total,title) 逐步上报，供前端进度条。"""
    calls: list[tuple[int, int, str]] = []
    plan = _plan(
        _step("第一步", "describe", ["value"]),
        _step("第二步", "describe", ["age"]),
    )

    PipelineExecutor().execute(
        DF, plan, artifact_dir=tmp_path, on_step=lambda i, total, title: calls.append((i, total, title))
    )

    assert calls == [(0, 2, "第一步"), (1, 2, "第二步")]

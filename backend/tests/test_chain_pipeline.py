"""037 链间管道：impute 的插补结果供后续步骤使用（工作链数据流动）。"""
from __future__ import annotations

import json

import pandas as pd

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.pipeline.executor import PipelineExecutor


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A", "B", "A", "B"],
            "value": [1.0, float("nan"), 3.0, 4.0],
        }
    )


def _impute_step() -> PlanStep:
    return PlanStep(
        title="插补 value",
        method="impute",
        target_columns=["value"],
        chart_type="none",
        params={"columns": ["value"], "method": "mice", "m": 3},
        rationale="缺失处理",
    )


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="插补后描述",
        steps=[
            _impute_step(),
            PlanStep(
                title="描述 value",
                method="describe",
                target_columns=["value"],
                chart_type="none",
                params={},
                rationale="插补后分布",
            ),
        ],
    )


def test_pipeline_impute_feeds_describe(tmp_path) -> None:
    """B1: impute→describe 链中 describe 作用于插补后数据（count=4 而非 3）。"""
    report = PipelineExecutor().execute(_df(), _plan(), tmp_path)

    assert report.steps[0].status == "success"
    assert report.steps[1].status == "success"
    describe_row = report.steps[1].result["table"]["rows"][0]
    # 缺陷实现：describe 用原 df → 有效计数 3；管道生效后插补值参与统计
    assert describe_row["count"] == 4


def test_single_impute_step_unchanged(tmp_path) -> None:
    """B2: 单独 impute 步骤行为不变（仍产出 imputed_dataset）。"""
    plan = AnalysisPlan(message="m", steps=[_impute_step()])

    report = PipelineExecutor().execute(_df(), plan, tmp_path)

    result = report.steps[0].result
    assert result["imputed_dataset"]["path"].endswith("imputed_step_0.csv")
    assert result["missing_after"]["value"] == 0


def test_next_frame_not_in_report_json(tmp_path) -> None:
    """B3: _next_frame 不泄漏进报告 JSON（严格序列化仍通过）。

    注意：pytest 临时目录名含该子串，断言须针对 result 键而非全文搜索。
    """
    report = PipelineExecutor().execute(_df(), _plan(), tmp_path)

    dump = report.model_dump()
    for step in dump["steps"]:
        assert "_next_frame" not in (step.get("result") or {})
        if step.get("table"):
            assert "_next_frame" not in json.dumps(step["table"], default=str)
    # 整体严格序列化仍通过
    json.dumps(dump, default=str, allow_nan=False)

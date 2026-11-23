"""027 B16–B20：生存分析的输入校验、工具分派、图表与能力披露。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from medsta.agents.discussion import PlanStep
from medsta.app import create_app
from medsta.stats.registry import execute_step
from medsta.stats.survival import survival_analysis

TIME_14_2 = np.array([10, 10, 13, 18, 25, 29, 30, 33, 46, 50, 54, 68, 71, 88, 95], dtype=float)
EVENT_14_2 = np.array([1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0], dtype=int)
TIME_GT5 = np.array(
    [5, 9, 13, 13, 14, 15, 19, 20, 21, 22, 24, 25, 26, 27, 28, 32, 47, 52, 54, 60, 86],
    dtype=float,
)


def _frame() -> pd.DataFrame:
    time = np.concatenate([TIME_14_2, TIME_GT5])
    event = np.concatenate([EVENT_14_2, np.ones(len(TIME_GT5), dtype=int)])
    group = np.array(["le2cm"] * len(TIME_14_2) + ["gt5cm"] * len(TIME_GT5))
    return pd.DataFrame({"time": time, "event": event, "group": group})


def _step(**params) -> PlanStep:
    return PlanStep(
        title="生存分析",
        method="survival_analysis",
        target_columns=["time", "event"],
        chart_type="none",
        params=params,
        rationale="随访资料",
    )


def test_rejects_non_binary_event() -> None:
    """B16: 事件列只能取 0/1。"""
    frame = pd.DataFrame({"time": [1.0, 2.0, 3.0, 4.0], "event": [1, 2, 0, 1]})

    with pytest.raises(ValueError) as excinfo:
        survival_analysis(frame, _step(), {})

    assert "0/1" in str(excinfo.value)


def test_rejects_all_censored() -> None:
    """B17: 全删失（事件数=0）时报可读错误。"""
    frame = pd.DataFrame({"time": [1.0, 2.0, 3.0, 4.0], "event": [0, 0, 0, 0]})

    with pytest.raises(ValueError) as excinfo:
        survival_analysis(frame, _step(), {})

    assert "删失" in str(excinfo.value)


def test_rejects_negative_time() -> None:
    """B18: 随访时间为负时报可读错误。"""
    frame = pd.DataFrame({"time": [-1.0, 2.0, 3.0, 4.0], "event": [1, 1, 0, 1]})

    with pytest.raises(ValueError) as excinfo:
        survival_analysis(frame, _step(), {})

    assert "负" in str(excinfo.value)


def test_grouped_km_reports_each_group() -> None:
    """工具按 group_col 分派分组 KM。"""
    frame = _frame()

    step = _step(group_col="group", method="km")
    result = survival_analysis(frame, step, step.params)

    assert result["method"] == "km"
    assert set(result["groups"]) == {"le2cm", "gt5cm"}
    assert result["groups"]["le2cm"]["n"] == 15
    assert result["groups"]["gt5cm"]["n"] == 21


def test_logrank_dispatch_and_significance() -> None:
    """工具按 group_col 分派 log-rank 并附带显著性判定。"""
    step = _step(group_col="group", method="logrank")
    result = survival_analysis(_frame(), step, step.params)

    assert result["method"] == "logrank"
    assert result["df"] == 1
    assert "significant" in result
    assert len(result["table"]["rows"]) == 2


def test_cox_dispatch_requires_covariates() -> None:
    """Cox 分派缺少协变量时报错。"""
    with pytest.raises(ValueError) as excinfo:
        step = _step(method="cox")
        survival_analysis(_frame(), step, step.params)

    assert "协变量" in str(excinfo.value)


def test_survival_curve_rendered(tmp_path) -> None:
    """B19: survival_curve 图表可渲染为 PNG（阶梯 + 删失标记 + 多组）。"""
    frame = _frame()
    step = _step(group_col="group", method="km").model_copy(
        update={"chart_type": "survival_curve"}
    )

    result, artifact = execute_step(frame, step, tmp_path, 0)

    assert artifact is not None and artifact.endswith("survival_curve.png")
    assert (tmp_path / artifact).exists()
    assert result["groups"]["le2cm"]["points"]


def test_capabilities_lists_survival_and_drops_planned() -> None:
    """B20: survival_analysis 进入 tools，planned 中不再出现。"""
    client = TestClient(create_app())
    body = client.get("/capabilities").json()

    tools = {tool["name"] for tool in body["tools"]}
    planned = {item["name"] for item in body["planned"]}

    assert "survival_analysis" in tools
    assert "survival_analysis" not in planned
    assert "competing_risk" in planned
    assert "survival_curve" in {chart["name"] for chart in body["charts"]}

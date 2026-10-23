"""029 B1–B8：Estimand 契约与 sap_status 判定。"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest
from pydantic import ValidationError

from medsta.agents.discussion import (
    SAP_STATUS_DECLARED,
    SAP_STATUS_EXPLORATORY,
    AnalysisPlan,
    DiscussionAgent,
    EstimandSpec,
    PlanStep,
    sap_status_of,
)
from medsta.data.profiler import profile_dataframe

from tests.conftest import RecordingFakeRequest

STEP = {
    "title": "分布统计",
    "method": "describe",
    "target_columns": ["value"],
    "chart_type": "none",
    "params": {},
    "rationale": "先看分布",
}

FULL_ESTIMAND = {
    "population": "接受手术的成年患者",
    "variable": "术后 12 个月 JOA 评分",
    "treatment": "手术组 vs 保守治疗组",
    "intercurrent_events": [
        {"event": "中途停药", "strategy": "treatment-policy"},
    ],
    "summary_measure": "两组均数差",
}


def _plan(estimand: EstimandSpec | None = None) -> AnalysisPlan:
    return AnalysisPlan(
        message="方案",
        steps=[PlanStep(**STEP)],
        options=[],
        estimand=estimand,
    )


def test_complete_estimand_is_declared() -> None:
    """B1: 四个文本要素齐全 → estimand_declared。"""
    plan = _plan(EstimandSpec(**FULL_ESTIMAND))

    assert sap_status_of(plan) == SAP_STATUS_DECLARED


def test_missing_factor_is_exploratory() -> None:
    """B2: 缺任一文本要素 → exploratory。"""
    payload = {**FULL_ESTIMAND, "treatment": "  "}

    assert sap_status_of(_plan(EstimandSpec(**payload))) == SAP_STATUS_EXPLORATORY


def test_absent_estimand_is_exploratory() -> None:
    """B3: 完全未声明 → exploratory。"""
    assert sap_status_of(_plan(None)) == SAP_STATUS_EXPLORATORY


def test_empty_intercurrent_events_still_declared() -> None:
    """B4: 无伴发事件（空列表）不影响状态判定。"""
    payload = {**FULL_ESTIMAND, "intercurrent_events": []}

    assert sap_status_of(_plan(EstimandSpec(**payload))) == SAP_STATUS_DECLARED


def test_invalid_strategy_rejected() -> None:
    """B5: 伴发事件策略必须是五种之一。"""
    with pytest.raises(ValidationError):
        EstimandSpec(
            population="成人",
            variable="评分",
            treatment="A vs B",
            summary_measure="均值差",
            intercurrent_events=[{"event": "停药", "strategy": "whatever"}],
        )


def _agent(payload: dict) -> DiscussionAgent:
    return DiscussionAgent(request_factory=lambda: RecordingFakeRequest(payload))


def test_model_output_includes_estimand(sample_df: pd.DataFrame) -> None:
    """B6: 模型输出含 estimand 时进入 plan。"""
    payload = {
        "message": "方案",
        "steps": [STEP],
        "options": [{"id": "go", "label": "执行", "action": "confirm", "description": ""}],
        "estimand": FULL_ESTIMAND,
    }

    plan = _agent(payload).draft_plan(profile_dataframe(sample_df), "分析 value")

    assert plan.estimand is not None
    assert plan.estimand.population == FULL_ESTIMAND["population"]
    assert plan.estimand.intercurrent_events[0].strategy == "treatment-policy"
    assert sap_status_of(plan) == SAP_STATUS_DECLARED


def test_plan_without_estimand_still_works(sample_df: pd.DataFrame) -> None:
    """B8: 模型不输出 estimand 时方案正常生成。"""
    payload = {
        "message": "方案",
        "steps": [STEP],
        "options": [{"id": "go", "label": "执行", "action": "confirm", "description": ""}],
    }

    plan = _agent(payload).draft_plan(profile_dataframe(sample_df), "分析 value")

    assert plan.estimand is None
    assert sap_status_of(plan) == SAP_STATUS_EXPLORATORY


class _StreamGateway:
    """最小流式网关：直接返回带 estimand 的方案。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def request_structured_stream(self, model, *, fields, input, info, instruct, on_delta=None):
        return model.model_validate(self._payload)

    def __getattr__(self, name: str):
        raise AttributeError(name)


async def test_stream_path_keeps_estimand(sample_df: pd.DataFrame) -> None:
    """B7: 流式路径同样保留 estimand。"""
    payload = {
        "message": "方案",
        "steps": [STEP],
        "options": [{"id": "go", "label": "执行", "action": "confirm", "description": ""}],
        "estimand": FULL_ESTIMAND,
    }
    agent = DiscussionAgent(gateway=_StreamGateway(payload))

    plan = await agent.draft_plan_stream(
        profile=profile_dataframe(sample_df), user_request="分析 value"
    )

    assert plan.estimand is not None
    assert sap_status_of(plan) == SAP_STATUS_DECLARED


def test_plan_event_carries_estimand(client, app, session_id: str) -> None:
    """B9: plan 事件下发 estimand 与 sap_status。"""
    from tests.helpers import collect_until, upload_csv

    payload = {
        "message": "方案",
        "steps": [STEP],
        "options": [{"id": "go", "label": "执行", "action": "confirm", "description": ""}],
        "estimand": FULL_ESTIMAND,
    }
    app.state.service.set_agent(_agent(payload))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value"})
        collect_until(ws, {"type_review"})
        ws.send_json(
            {
                "type": "type_confirm",
                "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
            }
        )
        _, plan_event = collect_until(ws, {"plan"})

    assert plan_event["estimand"]["population"] == FULL_ESTIMAND["population"]
    assert plan_event["estimand"]["intercurrent_events"][0]["strategy"] == "treatment-policy"
    assert plan_event["sap_status"] == SAP_STATUS_DECLARED


def test_evidence_carries_estimand(sample_df: pd.DataFrame) -> None:
    """B10: 证据包含 estimand 与 sap_status，供解读引用。"""
    from medsta.agents.interpretation import build_evidence

    report = {
        "steps": [
            {
                "title": "分布统计",
                "method": "describe",
                "status": "success",
                "result": {"n": 6},
                "artifact": None,
            }
        ]
    }
    plan = _plan(EstimandSpec(**FULL_ESTIMAND))

    evidence = build_evidence(report, plan, profile_dataframe(sample_df))

    assert evidence["sap_status"] == SAP_STATUS_DECLARED
    assert evidence["estimand"]["population"] == FULL_ESTIMAND["population"]
    assert evidence["estimand"]["intercurrent_events"][0]["strategy"] == "treatment-policy"


def test_evidence_without_estimand_marks_exploratory(sample_df: pd.DataFrame) -> None:
    """B10: 未声明时证据标 exploratory 且 estimand 为 None。"""
    from medsta.agents.interpretation import build_evidence

    evidence = build_evidence({"steps": []}, _plan(None), profile_dataframe(sample_df))

    assert evidence["estimand"] is None
    assert evidence["sap_status"] == SAP_STATUS_EXPLORATORY


def test_no_confirmatory_wording_in_source() -> None:
    """B12: 后端文案不得把本系统产出描述为 pre-specified / 确证性。"""
    project = pathlib.Path(__file__).resolve().parents[2]
    roots = [
        (project / "backend" / "src" / "medsta", "*.py"),
        (project / "frontend" / "src", "*.tsx"),
    ]
    offenders: list[str] = []
    for root, pattern in roots:
        for path in root.rglob(pattern):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                lowered = stripped.lower()
                if "pre-specified" in lowered or "prespecified" in lowered:
                    offenders.append(f"{path.name}: {stripped}")
                if "确证性" in stripped and "不" not in stripped and "未" not in stripped:
                    offenders.append(f"{path.name}: {stripped}")
    assert offenders == []

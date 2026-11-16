"""022 B9–B13：解释推送与交付态答疑分流（WS 契约）。"""
from __future__ import annotations

import pandas as pd
import pytest

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.agents.interpretation import EXPLORATORY_CAVEAT, InterpretationAgent
from medsta.config import InterpretConfig
from medsta.session.manager import SessionStatus, manager
from tests.conftest import RecordingFakeRequest
from tests.helpers import PLAN_TABLE_ONLY, collect_until, drive_to_review, fake_agent, upload_csv

INTERPRET_PAYLOAD = {
    "summary": "本次描述统计已完成，分布需结合临床意义判断。",
    "steps": [{"step_index": 0, "finding": "该步骤已完成（n=6）。", "caveat": ""}],
    "caveats": ["样本量有限"],
}

ANSWER_PAYLOAD = {
    "answer": "该步骤只做描述统计，未做显著性检验，因此没有 p 值可解读。",
    "caveats": [],
}


def make_interpret_agent(payload: dict | None = None) -> InterpretationAgent:
    return InterpretationAgent(
        request_factory=lambda: RecordingFakeRequest(payload or INTERPRET_PAYLOAD)
    )


def test_review_then_interpretation_frame(client, app, session_id: str) -> None:
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    app.state.service.set_interpret_agent(make_interpret_agent(), InterpretConfig(max_sentences=1))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        _, review = drive_to_review(ws)
        assert review["type"] == "review_request"
        frames, event = collect_until(ws, {"interpretation"})

    assert event["summary"]
    assert event["steps"][0]["step_index"] == 0
    assert event["caveats"][-1] == EXPLORATORY_CAVEAT
    assert event["unverified_numbers"] == []


def test_disabled_interpret_emits_no_frame(client, app, session_id: str) -> None:
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    app.state.service.set_interpret_agent(
        make_interpret_agent(), InterpretConfig(enabled=False)
    )
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        frames, _ = drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        delivered_frames, delivered = collect_until(ws, {"delivered"})

    assert delivered["type"] == "delivered"
    assert all(frame.get("type") != "interpretation" for frame in frames + delivered_frames)


def test_delivered_chat_answers_without_plan(client, app, session_id: str) -> None:
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    app.state.service.set_interpret_agent(
        make_interpret_agent(ANSWER_PAYLOAD), InterpretConfig()
    )
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        collect_until(ws, {"delivered"})

        ws.send_json({"type": "chat", "content": "这个结果有 p 值吗？"})
        _, reply = collect_until(ws, {"answer", "plan"})

    assert reply["type"] == "answer"
    assert "p 值" in reply["answer"]
    assert manager.get(session_id).status == SessionStatus.DELIVERED


def test_delivered_revise_returns_to_discussion(client, app, session_id: str) -> None:
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    app.state.service.set_interpret_agent(make_interpret_agent(), InterpretConfig())
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        collect_until(ws, {"delivered"})

        ws.send_json({"type": "review", "decision": "revise", "content": "改用相关性分析"})
        _, back = collect_until(ws, {"back_to_discussion", "error"})

    assert back["type"] == "back_to_discussion"
    assert manager.get(session_id).status == SessionStatus.DISCUSSING


@pytest.mark.asyncio
async def test_stale_interpretation_dropped(app, data_root, sample_df: pd.DataFrame) -> None:
    service = app.state.service
    service.set_interpret_agent(make_interpret_agent(), InterpretConfig(max_sentences=1))
    session_id = service.create_session()
    service.attach_dataframe(session_id, df=sample_df, dataset_path="stale.csv")
    session = manager.get(session_id)
    assert session is not None

    service._plans[session_id] = AnalysisPlan(
        message="描述分布",
        steps=[
            PlanStep(
                title="当前步骤",
                method="describe",
                target_columns=["value"],
                chart_type="none",
                params={},
                rationale="先看分布",
            )
        ],
    )
    service._reports[session_id] = {
        "steps": [{"title": "当前步骤", "method": "describe", "status": "success", "result": {}}]
    }
    stale_report = {
        "steps": [{"title": "旧步骤", "method": "describe", "status": "success", "result": {}}]
    }

    frames: list[dict] = []

    async def send(payload: dict) -> None:
        frames.append(payload)

    service._start_interpretation(session_id, stale_report, session, send)
    await service.wait_idle(session_id)

    assert [frame for frame in frames if frame.get("type") == "interpretation"] == []

"""019 B16–B17：WebSocket 全事件链、中断/继续与错误码契约。"""
from __future__ import annotations

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.manager import manager

from tests.helpers import (
    PLAN_WITH_CHART,
    collect_until,
    drive_to_review,
    fake_agent,
    upload_csv,
)


def test_full_event_chain_upload_to_delivery(client, app, session_id: str) -> None:
    """B16: type_review → plan → chart_config → progress → review_request → delivered。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value 的分布"})
        _, review_event = collect_until(ws, {"type_review"})
        assert {column["name"] for column in review_event["columns"]} == {"group", "value", "age"}
        assert all({"name", "type", "missing"} <= set(column) for column in review_event["columns"])
        assert "确认" in review_event["message"]

        ws.send_json(
            {
                "type": "type_confirm",
                "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
            }
        )
        frames, plan = collect_until(ws, {"plan"})
        assert any(frame["type"] == "type_confirmed" for frame in frames)
        assert plan["steps"][0]["method"] == "describe"
        assert plan["steps"][0]["step_id"] == "step_1"
        assert any(option["action"] == "confirm" for option in plan["options"])
        assert any(frame["type"] == "progress" and frame["stage"] == "thinking" for frame in frames)

        ws.send_json({"type": "confirm_plan"})
        _, config = collect_until(ws, {"chart_config"})
        assert config["steps"][0]["default_chart"] == "histogram"
        assert config["multi_chart"] is False
        assert config["alpha"] == 0.05
        assert config["correction"] == "holm"

        ws.send_json(
            {
                "type": "chart_choice",
                "use_default": True,
                "layout": "separate",
                "alpha": 0.05,
                "correction": "holm",
            }
        )
        frames, review = collect_until(ws, {"review_request"})
        executing = [
            frame for frame in frames
            if frame["type"] == "progress" and frame["stage"] == "executing"
        ]
        assert executing and executing[0]["step"] == 1 and executing[0]["total"] == 1
        assert executing[0]["title"] == "分布统计"
        assert review["report"]["steps"][0]["artifact"] == "step_0_describe_histogram.png"

        ws.send_json({"type": "review", "decision": "accept"})
        _, delivered = collect_until(ws, {"delivered"})
        assert delivered["report"]["steps"][0]["status"] == "success"

    assert manager.get(session_id).status.value == "delivered"


def test_streaming_deltas_reach_client_before_plan(client, app, session_id: str) -> None:
    """B16: 模型流式增量以 stream 帧下发，客户端可边收边渲染。"""

    class _StreamGateway:
        async def request_structured_stream(
            self, schema, *, fields, input=None, info=None, instruct="", on_delta=None
        ):
            for piece in ("正在分析", "数据画像…"):
                if on_delta is not None:
                    await on_delta(piece)
            return AnalysisPlan(
                message="建议描述统计",
                steps=[
                    PlanStep(
                        title="描述统计",
                        method="describe",
                        target_columns=["value"],
                        chart_type="none",
                        params={},
                        rationale="连续变量先看分布",
                    )
                ],
                options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
            )

    app.state.service.set_agent(DiscussionAgent(gateway=_StreamGateway()))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value"})
        collect_until(ws, {"type_review"})
        ws.send_json(
            {"type": "type_confirm", "types": {"group": "categorical", "value": "continuous"}}
        )
        frames, plan = collect_until(ws, {"plan"})

    deltas = "".join(frame["delta"] for frame in frames if frame["type"] == "stream")
    assert deltas == "正在分析数据画像…"
    assert plan["message"] == "建议描述统计"


def test_chat_before_upload_returns_data_required(client, app, session_id: str) -> None:
    """B17: 未上传数据就讨论 → DATA_REQUIRED + 可操作 hint。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "开始分析"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "DATA_REQUIRED"
    assert error["hint"]
    assert error["detail"] is None


def test_chat_without_model_returns_model_unavailable(client, app, session_id: str) -> None:
    """B17: 模型未配置时给出配置指引，而不是静默失败。"""
    app.state.service.set_agent(None)
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "开始分析"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "MODEL_UNAVAILABLE"
    assert "LLM_API_KEY" in error["hint"]


def test_unknown_message_returns_protocol_unsupported(client, app, session_id: str) -> None:
    """B6(020): 未知消息类型是协议问题，不与方案校验失败混用。"""
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "magic", "content": "?"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "PROTOCOL_UNSUPPORTED"
    assert "magic" in error["message"]
    assert "协议" in error["hint"]


def test_unknown_session_returns_error_instead_of_crashing(client) -> None:
    """B17: 失效会话（刷新/重连）返回 NO_ACTIVE_RUN。"""
    with client.websocket_connect("/ws/not-a-session") as ws:
        ws.send_json({"type": "chat", "content": "你好"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "NO_ACTIVE_RUN"
    assert "会话不存在" in error["message"]


def test_confirm_without_plan_is_rejected(client, app, session_id: str) -> None:
    """B17: 没有方案就确认 → INVALID_PLAN。"""
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "confirm_plan"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "INVALID_PLAN"
    assert "方案" in error["message"]


def test_type_confirm_validates_column_and_type(client, app, session_id: str) -> None:
    """B17: 类型确认的错误可分类：未知列 COLUMN_NOT_FOUND、非法类型 INVALID_PARAM。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析"})
        collect_until(ws, {"type_review"})

        ws.send_json({"type": "type_confirm", "types": {"nope": "continuous"}})
        _, column_error = collect_until(ws, {"error"})
        assert column_error["code"] == "COLUMN_NOT_FOUND"

        ws.send_json({"type": "type_confirm", "types": {"group": "banana"}})
        _, type_error = collect_until(ws, {"error"})
        assert type_error["code"] == "INVALID_PARAM"


def test_interrupt_and_resume_without_active_run(client, app, session_id: str) -> None:
    """B17: 空闲态中断/继续都返回明确事件，不进入死锁。"""
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "interrupt"})
        _, interrupted = collect_until(ws, {"interrupted"})
        assert interrupted["stage"] == "thinking"

        ws.send_json({"type": "resume"})
        _, resumed = collect_until(ws, {"resumed"})
        assert resumed["stage"] == "discussion"
        assert manager.get(session_id).status.value == "discussing"


def test_review_without_execution_returns_no_active_run(client, app, session_id: str) -> None:
    """B17: 无执行时提交审阅 → NO_ACTIVE_RUN。"""
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "review", "decision": "accept"})
        _, error = collect_until(ws, {"error"})

    assert error["code"] == "NO_ACTIVE_RUN"


def test_revise_returns_to_discussion_with_note(client, app, session_id: str) -> None:
    """B17: 审阅提出修正 → back_to_discussion + 状态 discussing + 意见注入下一轮。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "revise", "content": "不要直方图"})
        _, back = collect_until(ws, {"back_to_discussion"})

        assert "继续讨论" in back["message"]
        assert manager.get(session_id).status.value == "discussing"

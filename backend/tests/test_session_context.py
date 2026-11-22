"""047 会话上下文实例：按 (owner, session) 分层，支撑报错后接续分析。

模型每次只看「画像 + 本轮诉求」时，报错后补充信息只能重新出方案；
上下文要能回答：图长什么样、哪几个节点成了、哪个失败了、用户补了什么。
"""
from __future__ import annotations

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.agents.flow import plan_flow
from medsta.session.context import (
    NODE_DONE,
    NODE_FAILED,
    NODE_PENDING,
    SessionContext,
    SessionContextStore,
)


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="先描述再比较",
        steps=[
            PlanStep(
                title="分布统计",
                method="describe",
                target_columns=["value"],
                chart_type="none",
                params={},
                rationale="先看分布",
            ),
            PlanStep(
                title="组间比较",
                method="group_compare",
                target_columns=["value"],
                chart_type="none",
                params={"group_column": "group"},
                rationale="两组比较",
                depends_on=[0],
            ),
        ],
    )


def test_store_layers_by_owner() -> None:
    """B8: 同一 session_id 在不同 owner 下是独立实例（多用户隔离预留）。"""
    store = SessionContextStore()
    alice = store.get("s1", "alice")
    bob = store.get("s1", "bob")

    assert alice is not bob
    alice.add_note("alice 的补充")
    assert "alice 的补充" not in bob.snapshot() or bob.snapshot() == ""
    assert len(store) == 2

    store.drop_owner("alice")
    assert store.find("s1") is bob
    store.drop_session("s1")
    assert len(store) == 0


def test_context_tracks_plan_and_node_states() -> None:
    """B8: 记录工作流与每节点状态/失败原因。"""
    plan = _plan()
    context = SessionContext(session_id="s1")
    context.describe_dataset(dataset_id="d1", name="cohort.csv", row_count=6, columns=3)
    context.set_plan(plan, plan_flow(plan)["nodes"])

    assert set(context.node_states.values()) == {NODE_PENDING}

    context.mark_node(0, NODE_DONE)
    context.mark_node(1, NODE_FAILED, {"code": "EXECUTION_FAILED", "message": "分组列不足 2 组"})

    text = context.snapshot()
    assert "已确认工作流（2 个节点" in text
    assert "[1] 分布统计（describe）" in text
    assert "✓" in text and "✗" in text
    assert "分组列不足 2 组" in text
    assert "cohort.csv" in text


def test_snapshot_is_bounded_and_includes_notes() -> None:
    """B8: 快照长度受限（不能把整段对话塞进 prompt），补充说明按时间累积。"""
    plan = _plan()
    context = SessionContext(session_id="s1")
    context.set_plan(plan, plan_flow(plan)["nodes"])
    for index in range(8):
        context.add_note(f"第{index}条补充说明" + "x" * 100)

    text = context.snapshot(limit=400)

    assert len(text) <= 400
    assert "第7条补充说明" in text  # 保留最近的补充
    assert len(snapshot_notes(context)) <= 5


def snapshot_notes(context: SessionContext) -> list[str]:
    return context.notes


def test_mark_node_success_clears_previous_error() -> None:
    """B8: 节点重跑成功后不再带旧错误（否则模型会针对已修复的问题再改）。"""
    context = SessionContext(session_id="s1")
    context.mark_node(1, NODE_FAILED, {"code": "EXECUTION_FAILED", "message": "旧错误"})
    context.mark_node(1, NODE_DONE)

    assert 1 not in context.node_errors
    assert context.node_states[1] == NODE_DONE


def test_service_context_written_and_released(tmp_path) -> None:
    """B8/B9: 确认方案后写入上下文；删除会话后上下文释放（不留内存残留）。"""
    from fastapi.testclient import TestClient

    from medsta.app import create_app
    from medsta.session.manager import manager
    from tests.helpers import collect_until, fake_agent, upload_csv

    payload = {
        "message": "先描述分布",
        "steps": [
            {
                "title": "分布统计",
                "method": "describe",
                "target_columns": ["value"],
                "chart_type": "none",
                "params": {},
                "rationale": "先看分布",
            }
        ],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }

    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(payload))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value 的分布"})
        collect_until(ws, {"type_review"})
        ws.send_json(
            {
                "type": "type_confirm",
                "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
            }
        )
        collect_until(ws, {"plan"})

    context = service._contexts.find(session_id)
    assert context is not None
    assert context.nodes and context.nodes[0]["method"] == "describe"
    assert context.turns == ["分析 value 的分布"]

    assert client.delete(f"/sessions/{session_id}").status_code == 200
    assert service._contexts.find(session_id) is None
    assert len(service._contexts) == 0

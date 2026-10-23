"""028 B14–B15：插补数据集注册与 dataset_added 事件。"""
from __future__ import annotations

from medsta.session.manager import manager

from tests.helpers import collect_until, drive_to_review, fake_agent, upload_csv

CSV_WITH_MISSING = (
    b"group,value,age\nA,1.5,20\nA,,21\nA,3.5,22\nB,4.5,41\nB,,42\nB,6.5,43\n"
)

PLAN_IMPUTE = {
    "message": "value 有缺失，先做 MICE 插补",
    "steps": [
        {
            "title": "缺失插补",
            "method": "impute",
            "target_columns": ["value"],
            "chart_type": "none",
            "params": {"method": "mice", "m": 3},
            "rationale": "3/6 行缺失，先插补再分析",
        }
    ],
    "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
}


def test_imputed_dataset_registered_without_switching(client, app, session_id: str) -> None:
    """B14: 执行后 datasets 增一项，active_dataset_id 保持不变。"""
    app.state.service.set_agent(fake_agent(PLAN_IMPUTE))
    upload_csv(client, session_id, content=CSV_WITH_MISSING)

    original = manager.get(session_id).active_dataset_id
    assert len(manager.get(session_id).datasets) == 1

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)

    session = manager.get(session_id)
    assert len(session.datasets) == 2
    assert session.active_dataset_id == original


def test_dataset_added_event_payload(client, app, session_id: str) -> None:
    """B15: 推送 dataset_added，含 dataset_id/name/profile/imputed/source。"""
    app.state.service.set_agent(fake_agent(PLAN_IMPUTE))
    upload_csv(client, session_id, content=CSV_WITH_MISSING)
    original = manager.get(session_id).active_dataset_id

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        _, review = drive_to_review(ws)
        assert review["type"] == "review_request"
        _, added = collect_until(ws, {"dataset_added"})

    assert added["type"] == "dataset_added"
    assert added["imputed"] is True
    assert added["source_dataset_id"] == original
    assert added["name"].endswith("（MICE 插补）")
    assert added["profile"]["row_count"] == 6
    assert added["profile"]["column_count"] == 3
    assert added["dataset_id"] != original


def test_plan_without_impute_emits_no_dataset(client, app, session_id: str) -> None:
    """B14: 普通计划不注册数据集、不推 dataset_added。"""
    from tests.helpers import PLAN_TABLE_ONLY

    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        frames, _ = drive_to_review(ws)

    assert all(frame.get("type") != "dataset_added" for frame in frames)
    assert len(manager.get(session_id).datasets) == 1


def test_capabilities_lists_impute(client) -> None:
    """B18: impute 进入 tools，planned 的 multiple_imputation 说明为完整 MI 未实现。"""
    body = client.get("/capabilities").json()
    tools = {tool["name"] for tool in body["tools"]}
    planned = {item["name"]: item for item in body["planned"]}

    assert "impute" in tools
    assert "multiple_imputation" in planned
    assert "未实现" in planned["multiple_imputation"]["description"]
    assert "单数据集" in planned["multiple_imputation"]["description"]

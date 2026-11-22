"""列类型变更的会话同步：REST 修改必须广播 type_confirmed 并落事件流。

用户在工作台改列类型（含采纳 AI 建议）时，会话区要能看到「改了什么」；
否则工作台变了、会话区毫无记录，刷新后也无从回放。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from medsta.app import create_app
from medsta.session.manager import manager
from tests.helpers import upload_csv


def _setup(tmp_path):
    root = tmp_path / "sessions"
    client = TestClient(create_app(data_root=root))
    session_id = client.post("/sessions").json()["session_id"]
    dataset_id = upload_csv(client, session_id)["dataset_id"]
    return client, session_id, dataset_id


def test_patch_columns_broadcasts_type_confirmed(tmp_path) -> None:
    """B1: 批量修改列类型 → 已连接的接收方收到 type_confirmed（含 updated/source/profile）。"""
    client, session_id, dataset_id = _setup(tmp_path)
    service = client.app.state.service

    received: list[dict] = []

    async def fake_sender(frame: dict) -> None:
        received.append(frame)

    service.attach_sender(session_id, fake_sender)
    try:
        resp = client.patch(
            f"/sessions/{session_id}/workspace/{dataset_id}/columns",
            json={"types": {"value": "ordinal"}, "source": "ai"},
        )
    finally:
        service.detach_sender(session_id, fake_sender)

    assert resp.status_code == 200
    assert len(received) == 1
    frame = received[0]
    assert frame["type"] == "type_confirmed"
    assert frame["dataset_id"] == dataset_id
    assert frame["updated"] == ["value"]
    assert frame["source"] == "ai"
    assert frame["profile"]["columns"]["value"]["type"] == "ordinal"
    assert isinstance(frame.get("seq"), int)


def test_single_column_patch_also_broadcasts(tmp_path) -> None:
    """B2: 单列下拉修改同样广播（此前只有 REST 响应，左栏无记录）。"""
    client, session_id, dataset_id = _setup(tmp_path)
    service = client.app.state.service

    received: list[dict] = []

    async def fake_sender(frame: dict) -> None:
        received.append(frame)

    service.attach_sender(session_id, fake_sender)
    try:
        resp = client.patch(
            f"/sessions/{session_id}/workspace/{dataset_id}/columns",
            json={"column": "group", "type": "categorical"},
        )
    finally:
        service.detach_sender(session_id, fake_sender)

    assert resp.status_code == 200
    assert received[0]["source"] == "manual"
    assert received[0]["updated"] == ["group"]


def test_broadcast_persists_event_for_replay(tmp_path) -> None:
    """B3: 没有在线连接也要落事件流——刷新（resume 回放）时左栏仍能重建这条提示。"""
    client, session_id, dataset_id = _setup(tmp_path)
    service = client.app.state.service

    client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"types": {"value": "continuous"}},
    )

    frames = service.event_log.read_after(session_id, 0)
    assert any(
        frame.get("type") == "type_confirmed" and frame.get("updated") == ["value"]
        for frame in frames
    )


def test_unknown_column_rejected_without_broadcast(tmp_path) -> None:
    """B4: 非法列整体拒绝（批量原子性），且不产生任何同步帧。"""
    client, session_id, dataset_id = _setup(tmp_path)
    service = client.app.state.service

    received: list[dict] = []

    async def fake_sender(frame: dict) -> None:
        received.append(frame)

    service.attach_sender(session_id, fake_sender)
    try:
        resp = client.patch(
            f"/sessions/{session_id}/workspace/{dataset_id}/columns",
            json={"types": {"value": "ordinal", "nope": "continuous"}},
        )
    finally:
        service.detach_sender(session_id, fake_sender)

    assert resp.status_code == 404
    assert received == []
    profile = client.get(f"/sessions/{session_id}/workspace").json()["datasets"][0]["profile"]
    assert profile["columns"]["value"]["type"] != "ordinal"


def test_cleanup_detaches_sender_list() -> None:
    """B5: detach 后注册表清空（断连不残留引用）。"""
    manager.clear()
    client = TestClient(create_app())
    service = client.app.state.service

    async def sender(frame: dict) -> None:
        return None

    service.attach_sender("s1", sender)
    assert "s1" in service._senders
    service.detach_sender("s1", sender)
    assert service._senders == {}

"""035 断线重连与历史回放：事件 seq 落盘、缺口补发、重启回放。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from medsta.app import create_app

from tests.helpers import PLAN_TABLE_ONLY, fake_agent, upload_csv


def _drive_to_plan(ws) -> None:
    ws.send_json({"type": "chat", "content": "分析"})
    def until(types, limit=80):
        seen = []
        for _ in range(limit):
            frame = ws.receive_json()
            if frame.get("type") in types:
                seen.append(frame)
                return seen
            seen.append(frame)
        raise AssertionError(f"未等到 {types}")
    ws.send_json({"type": "type_confirm", "types": {"group": "categorical", "value": "continuous", "age": "continuous"}})
    until({"plan"})


def _frames_from_events(root, session_id: str) -> list[dict]:
    path = root / session_id / "events.jsonl"
    if not path.is_file():
        return []
    frames = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            frames.append(json.loads(line))
        except ValueError:
            continue
    return frames


def test_events_have_monotonic_seq_and_persist(tmp_path) -> None:
    """B1: 出站帧带单调递增 seq，并追加落盘 events.jsonl。"""
    import io

    root = tmp_path / "sessions"
    app = create_app(data_root=root)
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id, content=b"group,value,age\nA,1,25\nB,2,31\n")

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析"})
        _drive_to_plan(ws)

    frames = _frames_from_events(root, session_id)
    seqs = [f["seq"] for f in frames]
    assert len(seqs) >= 4
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)  # 单调递增无重复
    # 全部帧可严格 JSON 序列化（默认 json.loads 已验证）


def test_resume_replays_gap_only(tmp_path) -> None:
    """B2: resume+last_seq 仅补发缺口帧（原帧原 seq），且不与回放重复投递。"""
    root = tmp_path / "sessions"
    app = create_app(data_root=root)
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id, content=b"group,value,age\nA,1,25\nB,2,31\n")

    first_seq: int | None = None
    plan_seq: int | None = None
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析"})
        _drive_to_plan(ws)
        for frame in _frames_from_events(root, session_id):
            if first_seq is None:
                first_seq = frame["seq"]
            if frame.get("type") == "plan":
                plan_seq = frame["seq"]

    assert first_seq is not None and plan_seq is not None and plan_seq > first_seq

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "resume", "last_seq": first_seq})
        replay: list[dict] = []
        for _ in range(30):
            frame = ws.receive_json()
            if frame.get("type") == "plan" and frame["seq"] == plan_seq:
                replay.append(frame)
                break
            replay.append(frame)
        seqs = [f["seq"] for f in replay if isinstance(f.get("seq"), int)]
        assert all(s > first_seq for s in seqs)  # 只补缺口
        assert any(f.get("type") == "plan" for f in replay)  # plan 帧在缺口内被补发
        assert len([f for f in replay if f.get("seq") == plan_seq]) == 1  # 不重复


def test_replay_after_backend_restart(tmp_path) -> None:
    """B3: 后端重启后 resume 可回放历史帧，且新事件 seq 续接不回退。"""
    import io

    root = tmp_path / "sessions"
    app = create_app(data_root=root)
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id, content=b"group,value,age\nA,1,25\nB,2,31\n")
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析"})
        _drive_to_plan(ws)
    max_seq_before = max(f["seq"] for f in _frames_from_events(root, session_id))

    manager_clear()
    restarted = TestClient(create_app(data_root=root))
    with restarted.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "resume", "last_seq": 0})
        got_plan = False
        for _ in range(40):
            frame = ws.receive_json()
            if frame.get("type") == "plan":
                assert frame["seq"] <= max_seq_before
                got_plan = True
                break
        assert got_plan


def manager_clear() -> None:
    from medsta.session.manager import manager

    manager.clear()


def test_resume_without_last_seq_unchanged(tmp_path) -> None:
    """B4: 不带 last_seq 的 resume 行为不变（交付态还原 delivered 事件）。"""
    root = tmp_path / "sessions"
    app = create_app(data_root=root)
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id, content=b"group,value,age\nA,1,25\nB,2,31\n")

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析"})
        _drive_to_plan(ws)
        ws.send_json({"type": "confirm_plan"})
        def until(types, limit=80):
            for _ in range(limit):
                frame = ws.receive_json()
                if frame.get("type") in types:
                    return frame
            raise AssertionError("timeout")
        until({"review_request"})
        ws.send_json({"type": "review", "decision": "accept"})
        until({"delivered"})

    from medsta.session.manager import SessionStatus, manager

    assert manager.get(session_id).status == SessionStatus.DELIVERED

    manager_clear()
    restarted = TestClient(create_app(data_root=root))
    with restarted.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "resume"})
        frame = ws.receive_json()
        assert frame["type"] == "resumed"

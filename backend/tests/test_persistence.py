"""032 会话持久化：快照落盘、原子写、重启恢复。

公共接口测试：TestClient / WS / 二次 create_app 模拟重启；快照文件直接断言。
注意：WS 帧到达客户端 ≠ 服务端 persist（await 链）已完成，断言快照前需轮询等待。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from medsta.app import create_app
from medsta.session.manager import manager

from tests.helpers import (
    PLAN_TABLE_ONLY,
    collect_until,
    drive_to_review,
    fake_agent,
    upload_csv,
)

TYPES = {"group": "categorical", "value": "continuous", "age": "continuous"}


def _wait_snapshot(root: Path, session_id: str, predicate, timeout: float = 3.0) -> dict:
    """轮询等待服务端 persist 完成并满足条件，返回最终快照。"""
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = _snapshot(root, session_id)
        if predicate(snapshot):
            return snapshot
        time.sleep(0.02)
    return snapshot


def _setup(tmp_path: Path) -> tuple[TestClient, str, Path]:
    root = tmp_path / "sessions"
    app = create_app(data_root=root)
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    return client, session_id, root


def _snapshot(root: Path, session_id: str) -> dict:
    return json.loads((root / session_id / "snapshot.json").read_text(encoding="utf-8"))


def test_snapshot_written_on_upload(tmp_path) -> None:
    """B1: 上传数据后生成快照，含数据集 id/name/路径与 type_confirmed=false。"""
    client, session_id, root = _setup(tmp_path)

    upload_csv(client, session_id)

    snapshot_path = root / session_id / "snapshot.json"
    assert snapshot_path.is_file()
    snapshot = _snapshot(root, session_id)
    assert snapshot["version"] == 1
    assert snapshot["status"] == "discussing"
    assert len(snapshot["datasets"]) == 1
    dataset = snapshot["datasets"][0]
    assert dataset["name"] == "cohort.csv"
    assert dataset["type_confirmed"] is False
    assert Path(dataset["path"]).is_file()


def test_snapshot_tracks_column_types(tmp_path) -> None:
    """B2: 列类型敲定（REST PATCH）后快照同步 type_confirmed 与逐列类型。"""
    client, session_id, root = _setup(tmp_path)
    uploaded = upload_csv(client, session_id)
    dataset_id = uploaded["dataset_id"]

    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"column": "value", "type": "ordinal"},
    )
    assert resp.status_code == 200

    dataset = _snapshot(root, session_id)["datasets"][0]
    assert dataset["type_confirmed"] is True
    assert dataset["column_types"]["value"] == "ordinal"


def test_snapshot_write_is_atomic(tmp_path, monkeypatch) -> None:
    """B3: 序列化失败时旧快照不受损、无残留临时文件、save 返回 False 不抛出。"""
    client, session_id, root = _setup(tmp_path)
    upload_csv(client, session_id)
    snapshot_path = root / session_id / "snapshot.json"
    original = snapshot_path.read_text(encoding="utf-8")
    store = client.app.state.service._store

    def boom(_payload: dict) -> str:
        raise RuntimeError("序列化失败")

    monkeypatch.setattr(store, "_serialize", boom)
    assert store.save(session_id, {"session_id": session_id}) is False
    assert snapshot_path.read_text(encoding="utf-8") == original
    assert list((root / session_id).glob("*.tmp")) == []


def test_corrupt_snapshot_skipped(tmp_path) -> None:
    """B7: 损坏快照在启动恢复时被跳过，不影响启动、不进入会话表。"""
    root = tmp_path / "sessions"
    (root / "broken-sid").mkdir(parents=True)
    (root / "broken-sid" / "snapshot.json").write_text("{not json", encoding="utf-8")

    create_app(data_root=root)

    assert manager.get("broken-sid") is None


def test_executing_snapshot_downgrades_to_discussing(tmp_path) -> None:
    """B8: status=executing 的快照恢复为 discussing（未完成执行不可恢复）。"""
    client, session_id, root = _setup(tmp_path)
    upload_csv(client, session_id)
    snapshot_path = root / session_id / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["status"] = "executing"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

    TestClient(create_app(data_root=root))

    assert manager.get(session_id).status.value == "discussing"


def test_session_restored_after_restart(tmp_path) -> None:
    """B4: 同一 data_root 重建应用后，会话/状态/工作区/列类型全部恢复。"""
    client, session_id, root = _setup(tmp_path)
    uploaded = upload_csv(client, session_id)
    dataset_id = uploaded["dataset_id"]
    client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"column": "value", "type": "ordinal"},
    )

    manager.clear()  # 模拟进程重启：内存态清空，恢复必须来自快照
    restarted = TestClient(create_app(data_root=root))

    session = manager.get(session_id)
    assert session is not None
    assert session.status.value == "discussing"
    assert session.active_dataset_id == dataset_id
    data = session.datasets[dataset_id]
    assert data.type_confirmed is True
    assert data.profile.columns["value"].type == "ordinal"
    assert data.df.shape == (6, 3)  # helpers CSV：6 行 3 列，从数据文件重建
    # 公共接口：激活工作区返回修正后的画像
    resp = restarted.post(f"/sessions/{session_id}/workspace/{dataset_id}/activate")
    assert resp.status_code == 200
    assert resp.json()["type_confirmed"] is True
    assert resp.json()["profile"]["columns"]["value"]["type"] == "ordinal"


def test_plan_restored_and_executable(tmp_path) -> None:
    """B6: 讨论产出 plan 后落盘；重启后 confirm_plan 可直接执行。"""
    client, session_id, root = _setup(tmp_path)
    client.app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value 的分布"})
        collect_until(ws, {"type_review"})
        ws.send_json({"type": "type_confirm", "types": TYPES})
        _, plan_event = collect_until(ws, {"plan"})
    assert plan_event["steps"][0]["method"] == "describe"

    snapshot = _snapshot(root, session_id)
    assert snapshot["plan"] is not None
    assert snapshot["plan"]["steps"][0]["method"] == "describe"

    manager.clear()  # 模拟进程重启
    restarted = TestClient(create_app(data_root=root))
    with restarted.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "confirm_plan"})
        _, review = collect_until(ws, {"review_request"})
        assert review["report"]["steps"][0]["method"] == "describe"


def test_report_and_delivery_restored(tmp_path) -> None:
    """B5: 报告落盘；交付态落盘；重启后 resume 还原交付（delivered 事件带 report）。"""
    client, session_id, root = _setup(tmp_path)
    client.app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        snapshot = _snapshot(root, session_id)
        assert snapshot["report"] is not None
        assert snapshot["report"]["steps"][0]["method"] == "describe"

        ws.send_json({"type": "review", "decision": "accept"})
        _, delivered = collect_until(ws, {"delivered"})
    snapshot = _wait_snapshot(root, session_id, lambda s: s["status"] == "delivered")
    assert snapshot["status"] == "delivered"

    manager.clear()  # 模拟进程重启
    restarted = TestClient(create_app(data_root=root))
    assert manager.get(session_id).status.value == "delivered"
    with restarted.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "resume"})
        _, resumed = collect_until(ws, {"resumed"})
        assert resumed["stage"] == "delivered"
        _, redelivered = collect_until(ws, {"delivered"})
        assert redelivered["report"]["steps"][0]["method"] == "describe"
    # 报告恢复后导出可用
    assert restarted.get(f"/export/{session_id}/0?format=csv").status_code == 200

"""001 后端骨架：FastAPI 应用公共接口测试。"""
import pathlib

from fastapi.testclient import TestClient

from medsta.app import create_app


def test_health(tmp_path: pathlib.Path) -> None:
    """B1: GET /health 返回 200 与 {"status": "ok"}"""
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_session(tmp_path: pathlib.Path) -> None:
    """B2: POST /sessions 创建会话，返回唯一 session_id 且 status 为 discussing"""
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    resp = client.post("/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"]
    assert body["status"] == "discussing"


def test_session_ids_unique(tmp_path: pathlib.Path) -> None:
    """B3: 两次创建会话得到不同 session_id"""
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    a = client.post("/sessions").json()["session_id"]
    b = client.post("/sessions").json()["session_id"]
    assert a != b

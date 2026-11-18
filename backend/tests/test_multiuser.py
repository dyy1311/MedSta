"""044 多用户：登录、会话归属隔离、列表、持久化。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from medsta.session.manager import manager
from tests.helpers import CSV, upload_csv

USERS = "alice:pw1,bob:pw2"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def multi_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDSTA_USERS", USERS)
    manager.clear()
    from medsta.app import create_app

    app = create_app(data_root=tmp_path / "sessions")
    client = TestClient(app)
    yield client, app, tmp_path
    manager.clear()


def _login(client: TestClient, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})


def _create_session(client: TestClient, token: str | None = None) -> str:
    headers = _headers(token) if token else {}
    resp = client.post("/sessions", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def test_login_identity(multi_env) -> None:
    """B2: 正确凭据换 token；错误凭据 401。"""
    client, _, _ = multi_env

    ok = _login(client, "alice", "pw1")
    assert ok.status_code == 200
    body = ok.json()
    assert body["username"] == "alice"
    assert body["token"]

    assert _login(client, "alice", "wrong").status_code == 401
    assert _login(client, "mallory", "x").status_code == 401


def test_anonymous_mode_has_no_login(tmp_path, monkeypatch) -> None:
    """B1: 未配置 MEDSTA_USERS 时 /auth/login 404（匿名模式行为不变）。"""
    monkeypatch.delenv("MEDSTA_USERS", raising=False)
    monkeypatch.delenv("MEDSTA_AUTH_TOKEN", raising=False)
    manager.clear()
    from medsta.app import create_app

    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    assert client.post("/auth/login", json={"username": "a", "password": "b"}).status_code == 404
    manager.clear()


def test_session_owner_isolation(multi_env) -> None:
    """B3: alice 的会话对 bob 一律 404（上传/报告/导出/列表不可见）。"""
    client, _, _ = multi_env
    token_a = _login(client, "alice", "pw1").json()["token"]
    token_b = _login(client, "bob", "pw2").json()["token"]

    sid = _create_session(client, token_a)
    upload_csv(client, sid, headers=_headers(token_a))

    up = client.post(
        f"/sessions/{sid}/data",
        files={"file": ("x.csv", CSV, "text/csv")},
        headers=_headers(token_b),
    )
    assert up.status_code == 404
    assert (
        client.get(f"/report/{sid}?style=lite&format=md", headers=_headers(token_b)).status_code
        == 404
    )
    assert client.get(f"/export/{sid}/0?format=csv", headers=_headers(token_b)).status_code == 404
    listed_b = client.get("/sessions", headers=_headers(token_b)).json()["sessions"]
    assert all(item["session_id"] != sid for item in listed_b)
    listed_a = client.get("/sessions", headers=_headers(token_a)).json()["sessions"]
    assert any(item["session_id"] == sid for item in listed_a)


def test_owner_persists_across_restart(multi_env) -> None:
    """B4: owner 随快照持久化，重启后归属保留。"""
    client, _, tmp_path = multi_env
    token_a = _login(client, "alice", "pw1").json()["token"]
    sid = _create_session(client, token_a)
    upload_csv(client, sid, headers=_headers(token_a))

    manager.clear()
    from medsta.app import create_app

    restarted = TestClient(create_app(data_root=tmp_path / "sessions"))
    token_b = _login(restarted, "bob", "pw2").json()["token"]
    assert (
        restarted.get(f"/report/{sid}?style=lite&format=md", headers=_headers(token_b)).status_code
        == 404
    )
    # 重启后令牌失效（内存表），需重新登录
    token_a2 = _login(restarted, "alice", "pw1").json()["token"]
    listed = restarted.get("/sessions", headers=_headers(token_a2)).json()["sessions"]
    assert any(item["session_id"] == sid for item in listed)

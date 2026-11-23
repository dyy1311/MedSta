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


def test_login_rate_limit_locks_window(multi_env) -> None:
    """批次11 生产加固：同 IP 60s 内 5 次失败后，正确凭据也被 429 拒绝。"""
    client, _, _ = multi_env

    for _ in range(5):
        assert _login(client, "alice", "wrong").status_code == 401

    locked = _login(client, "alice", "pw1")
    assert locked.status_code == 429
    assert "频繁" in locked.json()["detail"]


def test_login_success_resets_failure_counter(multi_env) -> None:
    """批次11：成功登录清零失败计数（暴力破解计数不跨成功会话累积）。"""
    client, _, _ = multi_env

    for _ in range(4):
        assert _login(client, "alice", "wrong").status_code == 401
    assert _login(client, "alice", "pw1").status_code == 200
    # 计数已清零：再次失败/成功不受历史影响
    assert _login(client, "alice", "wrong").status_code == 401
    assert _login(client, "alice", "pw1").status_code == 200


def test_delete_session_owner_isolation(multi_env) -> None:
    """批次12: bob 不能删除 alice 的会话（归属校验 404）；alice 自己可删。"""
    client, _, _ = multi_env
    alice_token = _login(client, "alice", "pw1").json()["token"]
    sid = client.post("/sessions", headers={"X-Auth-Token": alice_token}).json()["session_id"]

    bob_token = _login(client, "bob", "pw2").json()["token"]
    assert client.delete(f"/sessions/{sid}", headers={"X-Auth-Token": bob_token}).status_code == 404
    assert client.delete(f"/sessions/{sid}", headers={"X-Auth-Token": alice_token}).status_code == 200


def test_workspace_snapshot_owner_isolation(multi_env) -> None:
    """刷新恢复用的工作区快照同样受归属保护：他人会话 404，本人 200。"""
    client, _, _ = multi_env
    alice_token = _login(client, "alice", "pw1").json()["token"]
    sid = client.post("/sessions", headers={"X-Auth-Token": alice_token}).json()["session_id"]

    bob_token = _login(client, "bob", "pw2").json()["token"]
    assert (
        client.get(f"/sessions/{sid}/workspace", headers={"X-Auth-Token": bob_token}).status_code
        == 404
    )
    ok = client.get(f"/sessions/{sid}/workspace", headers={"X-Auth-Token": alice_token})
    assert ok.status_code == 200
    assert ok.json()["session_id"] == sid


def test_cleanup_duplicates_scoped_to_owner(multi_env) -> None:
    """批次13: 批量清理只作用于本人会话——alice 清理不动 bob 的同名数据会话。"""
    import io

    client, _, _ = multi_env
    alice_token = _login(client, "alice", "pw1").json()["token"]
    bob_token = _login(client, "bob", "pw2").json()["token"]

    def _bound(token: str, name: str) -> str:
        sid = client.post("/sessions", headers={"X-Auth-Token": token}).json()["session_id"]
        resp = client.post(
            f"/sessions/{sid}/data",
            files={"file": (name, io.BytesIO(b"g,v\nA,1\n"), "text/csv")},
            headers={"X-Auth-Token": token},
        )
        assert resp.status_code == 200
        return sid

    a1 = _bound(alice_token, "d.csv")
    a2 = _bound(alice_token, "d.csv")
    b1 = _bound(bob_token, "d.csv")

    resp = client.post("/sessions/cleanup_duplicates", headers={"X-Auth-Token": alice_token})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["deleted"]) == 1
    assert body["deleted"][0] in {a1, a2}
    assert b1 not in body["deleted"]  # bob 的同名会话不受波及
    alice_ids = {s["session_id"] for s in client.get(
        "/sessions", headers={"X-Auth-Token": alice_token}
    ).json()["sessions"]}
    assert alice_ids == ({a1, a2} - set(body["deleted"]))
    bob_ids = {s["session_id"] for s in client.get(
        "/sessions", headers={"X-Auth-Token": bob_token}
    ).json()["sessions"]}
    assert b1 in bob_ids


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


def test_static_shell_reachable_without_token(multi_env, tmp_path, monkeypatch) -> None:
    """prod 单端口 + 多用户：SPA 外壳必须可匿名取（否则登录页都打不开）。

    业务接口（/sessions、/data）仍要求有效令牌。
    """
    client, _, _ = multi_env
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    (dist / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr("medsta.app.FRONTEND_DIST", dist)
    from medsta.app import create_app

    prod = TestClient(create_app(data_root=tmp_path / "prod-sessions"))

    assert prod.get("/").status_code == 200
    assert prod.get("/assets/index-abc.js").status_code == 200
    assert prod.get("/sessions").status_code == 401
    assert prod.get("/data/whatever.png").status_code == 401

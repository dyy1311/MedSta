"""038 可选单令牌鉴权：env 开关，未配置时行为与现状完全一致。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from medsta.app import create_app


def _secured_app(tmp_path, monkeypatch, token="secret-token"):
    """构造开启鉴权的应用（monkeypatch env 后重建）。"""
    monkeypatch.setenv("MEDSTA_AUTH_TOKEN", token)
    return TestClient(create_app(data_root=tmp_path / "sessions"))


def _open_app(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDSTA_AUTH_TOKEN", raising=False)
    return TestClient(create_app(data_root=tmp_path / "sessions"))


def test_unconfigured_auth_keeps_existing_behavior(tmp_path, monkeypatch) -> None:
    """B1: 未配置令牌时鉴权完全关闭（创建会话与上传照常可用）。"""
    client = _open_app(tmp_path, monkeypatch)

    assert client.post("/sessions").status_code == 200
    assert client.get("/health").status_code == 200


def test_missing_token_401(tmp_path, monkeypatch) -> None:
    """B2a: 配置后无令牌/错令牌 → 401。"""
    client = _secured_app(tmp_path, monkeypatch, token="s3cret")

    assert client.post("/sessions").status_code == 401
    assert client.get("/templates").status_code == 401
    wrong = client.post("/sessions", headers={"X-Auth-Token": "nope"})
    assert wrong.status_code == 401


def test_correct_token_passes(tmp_path, monkeypatch) -> None:
    """B2b: 正确令牌（两种头格式）放行全部业务路由。"""
    client = _secured_app(tmp_path, monkeypatch, token="s3cret")

    ok_header = client.post("/sessions", headers={"X-Auth-Token": "s3cret"})
    assert ok_header.status_code == 200

    ok_bearer = client.get("/templates", headers={"Authorization": "Bearer s3cret"})
    assert ok_bearer.status_code == 200


def test_health_exempt(tmp_path, monkeypatch) -> None:
    """B3: /health 豁免（探活可用）。"""
    client = _secured_app(tmp_path, monkeypatch)

    assert client.get("/health").status_code == 200


def test_query_param_token_for_direct_links(tmp_path, monkeypatch) -> None:
    """P1(审查)：图片/下载直链无法携带 Authorization 头——?token= 与 WS 同口径放行。"""
    client = _secured_app(tmp_path, monkeypatch, token="s3cret")

    # 正确 ?token=：不再是 401（/data 静态目录，缺文件为 404）
    ok = client.get("/data/whatever.png?token=s3cret")
    assert ok.status_code != 401
    # 错误 ?token=：仍拒绝
    assert client.get("/data/whatever.png?token=wrong").status_code == 401


def test_ws_token_required(tmp_path, monkeypatch) -> None:
    """B4: WS 无 token → close(4401)；正确 token 正常收发。"""
    client = _secured_app(tmp_path, monkeypatch, token="s3cret")
    session_id = client.post(
        "/sessions", headers={"X-Auth-Token": "s3cret"}
    ).json()["session_id"]

    # 无 token：连接被拒（close code 4401）
    try:
        with client.websocket_connect(f"/ws/{session_id}") as ws:
            ws.receive_json()  # 期待收到 close 而非事件
        rejected = False
    except Exception:
        rejected = True
    assert rejected

    # 正确 token：正常收发（resume 会话）
    with client.websocket_connect(f"/ws/{session_id}?token=s3cret") as ws:
        ws.send_json({"type": "resume"})
        frame = ws.receive_json()
        assert frame["type"] == "resumed"


def test_spa_shell_public_but_data_protected(tmp_path, monkeypatch) -> None:
    """B5: 静态外壳（SPA 入口/构建产物）放行，业务数据（/data、/export…）仍受保护。

    外壳只有 index.html 与打包后的 JS/CSS，不含任何会话数据；若一并要求令牌，
    浏览器无法加载登录页与脚本（prod 单端口 + 鉴权会整页 401 白屏，无入口可登录）。
    """
    client = _secured_app(tmp_path, monkeypatch)

    assert client.get("/data/some/file.csv").status_code == 401
    assert client.get("/sessions").status_code == 401
    assert client.get("/").status_code != 401

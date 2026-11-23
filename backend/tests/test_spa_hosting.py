"""008 prod SPA 托管：静态页面回退与 API 豁免测试。"""
from pathlib import Path

from fastapi.testclient import TestClient

from medsta.app import create_app

INDEX_HTML = '<!doctype html><html><body><div id="root"></div></body></html>'


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (assets / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_spa_serves_index_and_assets(tmp_path, monkeypatch) -> None:
    """B6: dist 存在时 / 返回 index.html，/assets/* 返回静态资源"""
    dist = _make_dist(tmp_path)
    monkeypatch.setattr("medsta.app.FRONTEND_DIST", dist)
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text == INDEX_HTML
    resp = client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.text == "console.log(1)"


def test_spa_fallback_exempts_api_routes(tmp_path, monkeypatch) -> None:
    """B7: catch-all 豁免 /health /sessions /data /ws /docs /openapi.json"""
    dist = _make_dist(tmp_path)
    monkeypatch.setattr("medsta.app.FRONTEND_DIST", dist)
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
    resp = client.post("/sessions")
    assert resp.status_code == 200
    # API 前缀下无路由匹配的路径不落入 SPA fallback
    assert client.get("/sessions/abc/extra").status_code == 404
    assert client.get("/docs").status_code == 200


def test_spa_disabled_without_dist(monkeypatch, tmp_path) -> None:
    """B8: dist 不存在时不注册 SPA 路由，dev 行为不变"""
    monkeypatch.setattr("medsta.app.FRONTEND_DIST", tmp_path / "no-dist")
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404


def test_spa_fallback_blocks_path_traversal(tmp_path, monkeypatch) -> None:
    """P0: SPA catch-all 拒绝 .. 逃逸读取 dist 外文件，非法路径回退 index.html。"""
    dist = _make_dist(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    monkeypatch.setattr("medsta.app.FRONTEND_DIST", dist)
    client = TestClient(create_app())

    # URL 编码的 ..（%2F、%2E 两种写法）都不得读到 dist 外的 secret.txt
    for path in ("/..%2Fsecret.txt", "/..%2F..%2Fsecret.txt", "/%2E%2E/secret.txt"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.text == INDEX_HTML, path

    # dist 内子目录的合法文件仍可正常读取
    nested = dist / "nested"
    nested.mkdir()
    (nested / "page.html").write_text("<p>nested</p>", encoding="utf-8")
    resp = client.get("/nested/page.html")
    assert resp.status_code == 200
    assert resp.text == "<p>nested</p>"

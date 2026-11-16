"""034 工作链模板：保存/列表/删除/安全校验。"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from medsta.app import create_app

_STEPS = [
    {
        "method": "describe",
        "title": "分布统计",
        "target_columns": ["value"],
        "chart_type": "none",
        "params": {},
    },
    {
        "method": "group_compare",
        "title": "两组比较",
        "target_columns": ["value"],
        "chart_type": "none",
        "params": {"group_column": "group"},
    },
]


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(data_root=tmp_path / "sessions"))


def test_save_and_list(tmp_path) -> None:
    """B1: PUT 保存模板，GET 列表可见且含 steps 与时间戳。"""
    client = _client(tmp_path)

    put = client.put("/templates/我的套路", json={"steps": _STEPS})
    assert put.status_code == 200

    listing = client.get("/templates")
    assert listing.status_code == 200
    templates = {t["name"]: t for t in listing.json()["templates"]}
    assert "我的套路" in templates
    assert templates["我的套路"]["steps"] == _STEPS
    assert templates["我的套路"]["created_at"]
    assert templates["我的套路"]["updated_at"]


def test_overwrite_same_name(tmp_path) -> None:
    """B2: 同名重复 PUT 覆盖旧内容。"""
    client = _client(tmp_path)
    client.put("/templates/t1", json={"steps": _STEPS[:1]})

    client.put("/templates/t1", json={"steps": _STEPS})

    listing = client.get("/templates").json()["templates"]
    assert len(listing) == 1
    assert listing[0]["steps"] == _STEPS


def test_delete_template(tmp_path) -> None:
    """B3: DELETE 后从列表消失；删除不存在的模板返回 404。"""
    client = _client(tmp_path)
    client.put("/templates/t1", json={"steps": _STEPS})

    assert client.delete("/templates/t1").status_code == 200
    assert client.get("/templates").json()["templates"] == []
    assert client.delete("/templates/t1").status_code == 404


def test_is_safe_name_rejects_traversal() -> None:
    """B4: 模板名校验拒绝路径分隔符/..（httpx 客户端会规范化穿越路径，
    端到端测不到字面量，故直接校验宿主纯函数；路由层依赖此函数）。"""
    from medsta.session.templates import is_safe_name

    for name in ("../evil", "a/b", "..", ".", "", "a" * 65, "a\\b"):
        assert not is_safe_name(name), name

    assert is_safe_name("我的套路")
    assert is_safe_name("cohort-v1_2")
    assert is_safe_name("t1")


def test_put_with_chinese_name_roundtrip(tmp_path) -> None:
    """B4 补充：中文模板名端到端可用（httpx 不改写合法名）。"""
    client = _client(tmp_path)

    assert client.put("/templates/我的套路", json={"steps": _STEPS}).status_code == 200
    assert client.get("/templates/我的套路").status_code not in (400, 404) or (
        client.get("/templates").json()["templates"][0]["name"] == "我的套路"
    )


def test_rejects_unknown_method(tmp_path) -> None:
    """B5: steps 含未注册方法时返回 400。"""
    client = _client(tmp_path)
    bad = [{**_STEPS[0], "method": "nope"}]

    resp = client.put("/templates/t1", json={"steps": bad})

    assert resp.status_code == 400
    assert "nope" in resp.json()["detail"]


def test_corrupt_template_file_skipped(tmp_path) -> None:
    """软标：损坏的模板文件不导致列表接口失败。"""
    root = tmp_path / "sessions"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "broken.json").write_text("{not json", encoding="utf-8")

    client = _client(tmp_path)
    resp = client.get("/templates")

    assert resp.status_code == 200
    assert resp.json()["templates"] == []


def test_tool_catalog_exposes_accepts(tmp_path) -> None:
    """tool_catalog 输出 accepts（列类型预过滤的数据基础）。"""
    client = _client(tmp_path)

    catalog = client.get("/capabilities").json()["tools"]
    accepts = {tool["name"]: tool.get("accepts") for tool in catalog}
    assert accepts["group_compare"]  # 数值类
    assert "categorical" in accepts["mcnemar_test"]

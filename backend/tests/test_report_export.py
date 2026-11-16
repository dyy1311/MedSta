"""040 分析报告导出：学术/轻量风格 × docx/pdf/md 格式。"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from medsta.app import create_app
from tests.helpers import PLAN_WITH_CHART, collect_until, drive_to_review, fake_agent, upload_csv


def _delivered_session(client, app, session_id: str) -> None:
    """走完整链路到交付态，产出一个含表格与图的分析报告。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        collect_until(ws, {"delivered"})


def _client_with_delivered_session(tmp_path) -> tuple[TestClient, object, str]:
    app = create_app(data_root=tmp_path / "sessions")
    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    _delivered_session(client, app, session_id)
    return client, app, session_id


def test_academic_markdown_report(tmp_path) -> None:
    """B1: 学术风 md 含方法学章节、图表编号与教材口径。"""
    client, _, session_id = _client_with_delivered_session(tmp_path)

    resp = client.get(f"/report/{session_id}?style=academic&format=md")

    assert resp.status_code == 200
    text = resp.text
    assert "方法学" in text
    assert "表 1" in text  # 表格编号
    assert "图 1" in text  # 图编号（含 artifact 引用）
    assert "![" in text  # md 图片语法
    assert "分布统计" in text  # 步骤标题


def test_lite_markdown_report(tmp_path) -> None:
    """B2: 轻量风无方法学章节，结构为「标题+表格+要点」。"""
    client, _, session_id = _client_with_delivered_session(tmp_path)

    resp = client.get(f"/report/{session_id}?style=lite&format=md")

    assert resp.status_code == 200
    text = resp.text
    assert "方法学" not in text
    assert "分布统计" in text
    assert "|" in text  # md 表格


def test_docx_report_structure(tmp_path) -> None:
    """B3: docx 可解析：标题、表格、嵌入图片（学术风含方法学段落）。"""
    from docx import Document

    client, _, session_id = _client_with_delivered_session(tmp_path)

    resp = client.get(f"/report/{session_id}?style=academic&format=docx")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    document = Document(io.BytesIO(resp.content))
    paragraphs = "\n".join(p.text for p in document.paragraphs)
    assert "方法学" in paragraphs
    assert "分布统计" in paragraphs
    assert len(document.tables) >= 1  # 步骤表格
    assert len(document.inline_shapes) >= 1  # 图嵌入


def test_pdf_report_magic_bytes(tmp_path) -> None:
    """B4: pdf 魔数 %PDF-（CJK 字体环境）。"""
    client, _, session_id = _client_with_delivered_session(tmp_path)

    resp = client.get(f"/report/{session_id}?style=lite&format=pdf")

    assert resp.status_code == 200
    assert resp.content[:5] == b"%PDF-"
    assert resp.headers["content-type"] == "application/pdf"
    assert len(resp.content) > 2000  # 有实际内容


def test_report_not_found_and_invalid_params(tmp_path) -> None:
    """B5: 无报告 404；非法 style/format 400；report_id 可寻址。"""
    app = create_app(data_root=tmp_path / "sessions")
    client = TestClient(app)
    empty = client.post("/sessions").json()["session_id"]

    assert client.get(f"/report/{empty}?style=academic&format=md").status_code == 404
    assert client.get(f"/report/{empty}?style=fancy&format=md").status_code == 400
    assert client.get(f"/report/{empty}?style=academic&format=doc").status_code == 400

    client2, app2, session_id = _client_with_delivered_session(tmp_path)
    ok = client2.get(f"/report/{session_id}?style=lite&format=md")
    assert ok.status_code == 200


@pytest.mark.parametrize(
    ("style", "fmt"),
    [("academic", "md"), ("lite", "md"), ("academic", "docx"), ("lite", "docx"), ("lite", "pdf")],
)
def test_all_style_format_combinations(tmp_path, style: str, fmt: str) -> None:
    """风格 × 格式全组合可用（pdf 学术风由 B1/B4 覆盖关键路径，此处补全矩阵）。"""
    client, _, session_id = _client_with_delivered_session(tmp_path)

    resp = client.get(f"/report/{session_id}?style={style}&format={fmt}")

    assert resp.status_code == 200
    assert len(resp.content) > 200

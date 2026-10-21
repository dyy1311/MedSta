"""019 B15：交付与导出（CSV/XLSX、异常路径、文件名净化、delivered）。"""
from __future__ import annotations

import copy
import io
from urllib.parse import unquote

import pandas as pd

from medsta.session.manager import manager

from tests.helpers import (
    PLAN_NO_TABLE,
    PLAN_WITH_CHART,
    collect_until,
    drive_to_review,
    fake_agent,
    upload_csv,
)


def test_csv_export_is_utf8_sig_and_matches_table(client, app, session_id: str) -> None:
    """B15: CSV 带 BOM（Excel 中文兼容），内容与交付表格一致。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        _, review = drive_to_review(ws)
        step = review["report"]["steps"][0]
        assert step["table"]["columns"][:3] == ["column", "count", "mean"]

        resp = client.get(f"/export/{session_id}/0?format=csv")
        assert client.get(f"/export/{session_id}/0?format=pdf").status_code == 400
        assert client.get(f"/export/{session_id}/99?format=csv").status_code == 404

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.content.startswith(b"\xef\xbb\xbf")
    frame = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig")
    assert list(frame.columns) == ["column", "count", "mean", "median", "q25", "q75", "min", "max"]
    assert frame.iloc[0]["column"] == "value"
    assert frame.iloc[0]["count"] == 6
    assert frame.iloc[0]["mean"] == 4.0


def test_xlsx_export_is_readable(client, app, session_id: str) -> None:
    """B15: XLSX 可被 openpyxl/pandas 读回，表头与数据完整。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        resp = client.get(f"/export/{session_id}/0?format=xlsx")

    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    frame = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl")
    assert frame.iloc[0]["column"] == "value"
    assert frame.shape[0] == 1


def test_export_filename_is_sanitized(client, app, session_id: str) -> None:
    """B15: 步骤标题含斜杠时导出文件名被净化（不影响 Content-Disposition 解析）。"""
    payload = copy.deepcopy(PLAN_WITH_CHART)
    payload["steps"][0]["title"] = "A/B 分布"
    app.state.service.set_agent(fake_agent(payload))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        resp = client.get(f"/export/{session_id}/0?format=csv")

    header = resp.headers["content-disposition"]
    assert "%2F" not in header
    assert unquote(header.split("''", 1)[1]) == "A_B 分布.csv"


def test_export_without_report_returns_404(client, session_id: str) -> None:
    """B15: 没有执行报告时导出返回 404（未知会话同理）。"""
    assert client.get(f"/export/{session_id}/0?format=csv").status_code == 404
    assert client.get("/export/unknown/0?format=csv").status_code == 404


def test_export_step_without_table_returns_404(client, app, session_id: str) -> None:
    """B15: 无表格步骤（如正态性检验）导出返回 404 而不是空文件。"""
    app.state.service.set_agent(fake_agent(PLAN_NO_TABLE))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        _, review = drive_to_review(ws)
        assert review["report"]["steps"][0]["table"] is None
        resp = client.get(f"/export/{session_id}/0?format=csv")

    assert resp.status_code == 404
    assert "无可导出的表格" in resp.json()["detail"]


def test_accept_delivers_and_marks_session(client, app, session_id: str) -> None:
    """B15: 审阅接受 → delivered 事件 + 会话状态 delivered + 报告可复读。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        _, delivered = collect_until(ws, {"delivered"})

    assert delivered["report"]["steps"][0]["artifact"] == "step_0_describe_histogram.png"
    assert manager.get(session_id).status.value == "delivered"
    assert client.get(f"/export/{session_id}/0?format=csv").status_code == 200


def test_reports_are_scoped_per_session(client, app, session_id: str) -> None:
    """B15: 导出报告按会话隔离，另一个会话拿不到本次结果。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    other = client.post("/sessions").json()["session_id"]
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        assert client.get(f"/export/{session_id}/0?format=csv").status_code == 200
        assert client.get(f"/export/{other}/0?format=csv").status_code == 404

    assert other not in app.state.service.reports

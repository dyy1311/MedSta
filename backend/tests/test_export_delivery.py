"""019 B15：交付与导出（CSV/XLSX、异常路径、文件名净化、delivered）。"""
from __future__ import annotations

import copy
import io
import json
from urllib.parse import unquote

import pandas as pd

from medsta.session.manager import manager
from tests.helpers import (
    PLAN_NO_TABLE,
    PLAN_TABLE_ONLY,
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
        assert client.get(f"/export/{session_id}/0?format=docx").status_code == 400
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


def _inject_formula_report(app, session_id: str) -> None:
    """注入含公式注入载体的报告表格（模拟用户上传数据里的恶意标签）。"""
    app.state.service.reports[session_id] = {
        "steps": [
            {
                "title": "注入表",
                "method": "describe",
                "status": "success",
                "table": {
                    "columns": ["label", "value"],
                    "rows": [
                        {"label": "=cmd|' /C calc'!A0", "value": 1},
                        {"label": "+2+3", "value": -5.5},
                        {"label": "@SUM(A1)", "value": 2},
                        {"label": "正常文本", "value": 3.5},
                    ],
                },
                "result": {},
                "artifact": None,
                "error": None,
            }
        ]
    }


def test_csv_export_escapes_formula_prefixes(client, app, session_id: str) -> None:
    """P1: CSV 导出对以 = + - @ 开头的文本单元格加 ' 前缀；纯数值（含负数）不动。"""
    _inject_formula_report(app, session_id)

    resp = client.get(f"/export/{session_id}/0?format=csv")

    assert resp.status_code == 200
    frame = pd.read_csv(
        io.BytesIO(resp.content), encoding="utf-8-sig", dtype=str, keep_default_na=False
    )
    labels = frame["label"].tolist()
    assert labels[0].startswith("'=")
    assert labels[1].startswith("'+")
    assert labels[2].startswith("'@")
    assert labels[3] == "正常文本"
    # 数值列保持原样（负数不受影响；dtype=str 读回统一为浮点表示）
    assert [float(v) for v in frame["value"].tolist()] == [1.0, -5.5, 2.0, 3.5]


def test_xlsx_export_escapes_formula_prefixes(client, app, session_id: str) -> None:
    """P1: XLSX 导出同样转义公式前缀（openpyxl 会把 = 开头字符串存为公式）。"""
    _inject_formula_report(app, session_id)

    resp = client.get(f"/export/{session_id}/0?format=xlsx")

    assert resp.status_code == 200
    frame = pd.read_excel(io.BytesIO(resp.content), engine="openpyxl", dtype=str)
    labels = frame["label"].tolist()
    assert labels[0].startswith("'=")
    assert not any(str(cell).startswith("=") for cell in labels)


def _plan_describe(column: str) -> dict:
    return {
        "message": f"描述 {column}",
        "steps": [
            {
                "title": f"分布统计 {column}",
                "method": "describe",
                "target_columns": [column],
                "chart_type": "none",
                "params": {},
                "rationale": "连续变量先看分布",
            }
        ],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }


def test_export_by_report_id_targets_history_report(client, app, session_id: str) -> None:
    """M2: 带 report_id 的导出定位对应历史报告；缺省仍取最新报告。"""
    app.state.service.set_agent(fake_agent(_plan_describe("age")))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        _, review1 = drive_to_review(ws)
        rid1 = review1["report"]["report_id"]
        ws.send_json({"type": "review", "decision": "revise", "content": "换一列"})
        collect_until(ws, {"back_to_discussion"})

    app.state.service.set_agent(fake_agent(_plan_describe("value")))
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "看 value"})
        collect_until(ws, {"plan"})
        ws.send_json({"type": "confirm_plan"})
        _, review2 = collect_until(ws, {"review_request"})
        rid2 = review2["report"]["report_id"]

    assert rid1 and rid2 and rid1 != rid2
    old = client.get(f"/export/{session_id}/0?format=csv&report_id={rid1}")
    new = client.get(f"/export/{session_id}/0?format=csv&report_id={rid2}")
    default = client.get(f"/export/{session_id}/0?format=csv")
    assert old.status_code == 200 and new.status_code == 200
    assert b"age" in old.content
    assert b"value" in new.content
    assert b"value" in default.content  # 缺省 = 最新


def test_export_step_as_json(client, app, session_id: str) -> None:
    """B5: format=json 返回完整步骤 JSON（meta/table/result），严格 JSON 无 NaN。"""
    _inject_formula_report(app, session_id)

    resp = client.get(f"/export/{session_id}/0?format=json")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    payload = json.loads(resp.content.decode("utf-8"))
    assert payload["meta"]["step_index"] == 0
    assert payload["meta"]["tool"] == "describe"
    assert payload["table"]["columns"] == ["label", "value"]
    assert payload["result"] == {}


def test_export_chart_formats(client, app, session_id: str) -> None:
    """B6: 图导出支持 jpg/pdf/tif（按需重渲染），Content-Type 正确且内容非空。"""
    app.state.service.set_agent(fake_agent(PLAN_WITH_CHART))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)

    for fmt, ctype in (("jpg", "image/jpeg"), ("pdf", "application/pdf"), ("tif", "image/tiff")):
        resp = client.get(f"/export/{session_id}/0?format={fmt}")
        assert resp.status_code == 200, fmt
        assert resp.headers["content-type"].startswith(ctype), fmt
        assert len(resp.content) > 1000, fmt

    # 无图步骤导出图格式 → 404（类型已确认的会话：chat 直接出 plan，无 type_review）
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "只出统计表"})
        _, plan_event = collect_until(ws, {"plan"})
        assert plan_event["steps"][0]["method"] == "describe"
        ws.send_json({"type": "confirm_plan"})
        collect_until(ws, {"review_request"})
    assert client.get(f"/export/{session_id}/0?format=pdf").status_code == 404

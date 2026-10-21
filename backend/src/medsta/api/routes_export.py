"""分析结果导出：可视化表格 → CSV / Excel。"""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter()


@router.get("/export/{session_id}/{step_index}")
def export_step(session_id: str, step_index: int, request: Request, format: str = "csv"):
    service = request.app.state.service
    report = service.reports.get(session_id)
    if report is None or step_index >= len(report["steps"]):
        raise HTTPException(status_code=404, detail="执行报告不存在")
    step = report["steps"][step_index]
    table = step.get("table")
    if not table:
        raise HTTPException(status_code=404, detail="该步骤无可导出的表格")

    frame = pd.DataFrame(table["rows"], columns=table["columns"])
    safe_title = step.get("title", f"step_{step_index}").replace("/", "_")[:40]
    if format == "csv":
        content = frame.to_csv(index=False).encode("utf-8-sig")
        media = "text/csv; charset=utf-8"
        filename = f'{safe_title}.csv'
    elif format == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="result")
        content = buffer.getvalue()
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{safe_title}.xlsx"
    else:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式：{format}")

    from urllib.parse import quote

    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )

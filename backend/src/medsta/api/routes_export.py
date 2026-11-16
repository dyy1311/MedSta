"""分析结果导出：可视化表格 → CSV / Excel。"""
from __future__ import annotations

import io

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

router = APIRouter()

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _sanitize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """阻断电子表格公式注入：文本单元格以 = + - @ 开头时加 ' 前缀。

    数值单元格（含负数）保持原样；CSV 与 XLSX 共用，防止 Excel 打开导出件时执行公式。
    """
    sanitized = frame.copy()
    for column in sanitized.columns:
        sanitized[column] = [
            f"'{value}"
            if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES)
            else value
            for value in sanitized[column]
        ]
    return sanitized


@router.get("/export/{session_id}/{step_index}")
def export_step(
    session_id: str,
    step_index: int,
    request: Request,
    format: str = "csv",
    report_id: str | None = None,
):
    service = request.app.state.service
    if report_id:
        # 历史报告寻址导出（M2）：缺省仍取最新报告
        report = service.report_history.get(session_id, {}).get(report_id)
    else:
        report = service.reports.get(session_id)
    if report is None or step_index >= len(report["steps"]):
        raise HTTPException(status_code=404, detail="执行报告不存在")
    step = report["steps"][step_index]
    table = step.get("table")
    if not table:
        raise HTTPException(status_code=404, detail="该步骤无可导出的表格")

    frame = _sanitize_frame(pd.DataFrame(table["rows"], columns=table["columns"]))
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

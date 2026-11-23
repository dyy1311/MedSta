"""分析结果导出：可视化表格 → CSV / Excel / JSON；图表 → PNG / JPG / PDF / TIF。"""
from __future__ import annotations

import io
import json
import pathlib
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from medsta.session.manager import manager

router = APIRouter()

_IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "pdf": "application/pdf",
    "tif": "image/tiff",
}

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
    report_steps = (report or {}).get("steps") or []
    # 负数下标会让 Python 静默导出别的步骤：显式拒绝
    if report is None or step_index < 0 or step_index >= len(report_steps):
        raise HTTPException(status_code=404, detail="执行报告不存在")
    step = report["steps"][step_index]
    table = step.get("table")
    if not table:
        raise HTTPException(status_code=404, detail="该步骤无可导出的表格")

    frame = _sanitize_frame(pd.DataFrame(table["rows"], columns=table["columns"]))
    safe_title = step.get("title", f"step_{step_index}").replace("/", "_")[:40]

    if format == "json":
        # JSON 硬要求：分析数据以原始 JSON 输出（result + table + meta），前端不直接展示 JSON
        payload = {
            "meta": {
                "session_id": session_id,
                "step_index": step_index,
                "tool": step.get("method"),
                "title": step.get("title"),
                "status": step.get("status"),
                "report_id": report_id or (report.get("report_id") if isinstance(report, dict) else None),
            },
            "table": table,
            "result": step.get("result", {}),
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'{safe_title}.json')}"
            },
        )

    if format in _IMAGE_MEDIA_TYPES:
        # 图多格式导出：按需重渲染（PNG 落盘产物之外按请求生成）
        plan = request.app.state.service.plans.get(session_id)
        session = manager.get(session_id)
        if plan is None or session is None or session.data is None or step_index >= len(plan.steps):
            raise HTTPException(status_code=404, detail="该步骤无可导出的图表")
        plan_step = plan.steps[step_index]
        if plan_step.chart_type == "none":
            raise HTTPException(status_code=404, detail="该步骤未配置图表，无法导出图片")
        from medsta.stats.plotting import render_chart

        artifact_dir = pathlib.Path(session.data.artifact_dir)
        path = render_chart(
            session.data.df,
            plan_step,
            artifact_dir,
            step_index,
            result=step.get("result", {}),
            image_format=format,
        )
        return Response(
            content=path.read_bytes(),
            media_type=_IMAGE_MEDIA_TYPES[format],
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}"
            },
        )

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

    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )

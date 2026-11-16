"""分析报告导出路由（040）：风格（academic/lite）× 格式（docx/pdf/md）。"""
from __future__ import annotations

import pathlib
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from medsta.reporting import build_report_document, render_docx, render_markdown, render_pdf
from medsta.session.manager import manager

router = APIRouter()

_STYLES = ("academic", "lite")
_FORMATS = ("docx", "pdf", "md")


@router.get("/report/{session_id}")
async def export_report(
    session_id: str,
    request: Request,
    style: str = "academic",
    format: str = "docx",
    report_id: str | None = None,
) -> Response:
    service = request.app.state.service
    if style not in _STYLES:
        raise HTTPException(status_code=400, detail=f"未知风格：{style}（可选 {'/'.join(_STYLES)}）")
    if format not in _FORMATS:
        raise HTTPException(status_code=400, detail=f"未知格式：{format}（可选 {'/'.join(_FORMATS)}）")

    if report_id:
        report = service.report_history.get(session_id, {}).get(report_id)
    else:
        report = service.reports.get(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="该会话暂无可导出的分析报告")

    session = manager.get(session_id)
    plan = service.plans.get(session_id)
    artifact_dir = pathlib.Path(session.data.artifact_dir) if session and session.data else None
    label = session.data.name if session and session.data else session_id

    document = build_report_document(
        session_label=label,
        plan=plan,
        report=report,
        style=style,
        artifact_dir=artifact_dir,
    )
    safe_name = quote(f"分析报告-{label[:20]}")

    if format == "md":
        return Response(
            content=render_markdown(document),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}.md"},
        )
    if format == "docx":
        return Response(
            content=render_docx(document),
            media_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}.docx"
            },
        )
    try:
        payload = render_pdf(document)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}.pdf"},
    )

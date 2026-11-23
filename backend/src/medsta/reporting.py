"""分析报告导出（040）：风格（学术/轻量）× 格式（docx/pdf/md）。

架构：build_* 产出中间表示 ReportDocument（风格在构建层），
render_* 把中间表示渲染为字节/文本（格式在渲染层），2×3 正交。
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from medsta.stats.plotting import _detect_cjk_font


def _cjk_font_file() -> str | None:
    """返回 CJK 字体文件路径（reportlab 需要文件而非字体名）。"""
    name = _detect_cjk_font()
    if not name:
        return None
    try:
        from matplotlib import font_manager

        return str(font_manager.findfont(font_manager.FontProperties(family=name)))
    except Exception:
        return None


def _register_pdf_cjk_font(pdfmetrics: Any, ttf_font: Any) -> str:
    """注册 PDF 中文可选字体并返回字体名。

    优先系统 TrueType（.ttf，reportlab 不支持 CFF 轮廓的 .ttc/.otf），
    回退 reportlab 内置 Adobe CID 中文字体 STSong-Light（无需字体文件）。
    """
    try:
        from matplotlib import font_manager

        families = (
            "WenQuanYi Micro Hei",
            "WenQuanYi Zen Hei",
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
        )
        for family in families:
            try:
                path = font_manager.findfont(
                    font_manager.FontProperties(family=family), fallback_to_default=False
                )
            except Exception:
                continue
            if path and path.lower().endswith(".ttf") and Path(path).is_file():
                try:
                    pdfmetrics.registerFont(ttf_font("MedStaCJK", path))
                    return "MedStaCJK"
                except Exception:
                    continue
    except Exception:
        pass
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


@dataclass
class ReportSection:
    level: int  # 标题层级（1=章，2=节）
    title: str
    paragraphs: list[str] = field(default_factory=list)
    table: dict | None = None  # {columns: list, rows: list[list], caption: str}
    image: dict | None = None  # {path: Path, caption: str}
    notes: list[str] = field(default_factory=list)


@dataclass
class ReportDocument:
    title: str
    meta: list[tuple[str, str]] = field(default_factory=list)  # (标签, 值)
    sections: list[ReportSection] = field(default_factory=list)


def _step_tables(report: dict) -> list[tuple[Any, dict | None]]:
    """按步骤顺序取出 (step, table)；无表格的步骤跳过。"""
    pairs: list[tuple[Any, dict | None]] = []
    for step in report.get("steps", []):
        table = step.get("table")
        if isinstance(table, dict) and table.get("rows"):
            pairs.append((step, table))
        else:
            pairs.append((step, None))
    return pairs


def build_report_document(
    *,
    session_label: str,
    plan: Any,
    report: dict,
    style: str,
    artifact_dir: Path | None = None,
) -> ReportDocument:
    """构建报告中间表示：academic=方法学章节化+图表编号；lite=紧凑要点式。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = ReportDocument(
        title="MedSta 分析报告",
        meta=[("会话", session_label), ("导出时间", now), ("风格", "学术风" if style == "academic" else "轻量风")],
    )

    steps = report.get("steps", [])
    if style == "academic":
        # 方法学：每步的方法名与教材口径
        method = ReportSection(level=1, title="方法学")
        for step in steps:
            method.paragraphs.append(f"{step.get('title', '')}：{step.get('method', '')}")
            note = (step.get("result") or {}).get("method_note")
            if note:
                method.notes.append(f"{step.get('title', '')}——{note}")
        doc.sections.append(method)

        # 结果：表/图按出现顺序编号（表 1、图 1…）
        doc.sections.append(ReportSection(level=1, title="结果"))
        table_no = 0
        figure_no = 0
        for step, table in _step_tables(report):
            doc_section = ReportSection(level=2, title=str(step.get("title", "")))
            if table is not None:
                table_no += 1
                doc_section.table = {
                    "columns": list(table.get("columns", [])),
                    "rows": [list(row.values()) for row in table.get("rows", [])],
                    "caption": f"表 {table_no} {step.get('title', '')}",
                }
            if step.get("artifact") and artifact_dir is not None:
                figure_no += 1
                doc_section.image = {
                    "path": Path(artifact_dir) / str(step["artifact"]),
                    "caption": f"图 {figure_no} {step.get('title', '')}",
                }
            if not doc_section.table and not doc_section.image:
                continue
            doc.sections.append(doc_section)
    else:
        # 轻量：每步「标题+表格+图+要点」
        for step, table in _step_tables(report):
            section = ReportSection(level=2, title=str(step.get("title", "")))
            if table is not None:
                section.table = {
                    "columns": list(table.get("columns", [])),
                    "rows": [list(row.values()) for row in table.get("rows", [])],
                    "caption": str(step.get("title", "")),
                }
            if step.get("artifact") and artifact_dir is not None:
                section.image = {
                    "path": Path(artifact_dir) / str(step["artifact"]),
                    "caption": str(step.get("title", "")),
                }
            if not section.table and not section.image:
                continue
            doc.sections.append(section)

    return doc


def render_markdown(doc: ReportDocument) -> str:
    lines: list[str] = [f"# {doc.title}", ""]
    for label, value in doc.meta:
        lines.append(f"- **{label}**：{value}")
    lines.append("")
    for section in doc.sections:
        lines.append(f"{'#' * (section.level + 1)} {section.title}")
        lines.append("")
        for paragraph in section.paragraphs:
            lines.append(paragraph)
            lines.append("")
        for note in section.notes:
            lines.append(f"> {note}")
            lines.append("")
        if section.table is not None:
            columns = section.table["columns"]
            lines.append(f"**{section.table['caption']}**")
            lines.append("")
            lines.append("| " + " | ".join(str(c) for c in columns) + " |")
            lines.append("|" + "|".join(["---"] * len(columns)) + "|")
            for row in section.table["rows"]:
                lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
            lines.append("")
        if section.image is not None:
            lines.append(f"**{section.image['caption']}**")
            lines.append("")
            lines.append(f"![{section.image['caption']}]({Path(section.image['path']).name})")
            lines.append("")
    return "\n".join(lines)


def render_docx(doc: ReportDocument) -> bytes:
    import io as _io

    from docx import Document

    document = Document()
    document.add_heading(doc.title, level=0)
    for label, value in doc.meta:
        document.add_paragraph(f"{label}：{value}")
    for section in doc.sections:
        document.add_heading(section.title, level=min(section.level, 4))
        for paragraph in section.paragraphs:
            document.add_paragraph(paragraph)
        for note in section.notes:
            document.add_paragraph(note)
        if section.table is not None:
            columns = section.table["columns"]
            table = document.add_table(rows=1, cols=len(columns))
            table.style = "Table Grid"
            for cell, name in zip(table.rows[0].cells, columns):
                cell.text = str(name)
            for row in section.table["rows"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = str(value)
            document.add_paragraph(section.table["caption"])
        if section.image is not None:
            try:
                document.add_picture(str(section.image["path"]), width=None)
                document.add_paragraph(section.image["caption"])
            except (OSError, ValueError):
                document.add_paragraph(f"[图片缺失] {section.image['caption']}")
    buffer = _io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def render_pdf(doc: ReportDocument) -> bytes:
    import io as _io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font_name = _register_pdf_cjk_font(pdfmetrics, TTFont)

    body = ParagraphStyle("body", fontName=font_name, fontSize=10.5, leading=16)
    heading = ParagraphStyle("heading", fontName=font_name, fontSize=13, leading=18, spaceBefore=10)

    story: list[Any] = [
        Paragraph(
            doc.title,
            ParagraphStyle("title", fontName=font_name, fontSize=20, leading=26),
        ),
        Spacer(1, 0.4 * cm),
    ]
    for label, value in doc.meta:
        story.append(Paragraph(f"{label}：{value}", body))
    story.append(Spacer(1, 0.4 * cm))

    for section in doc.sections:
        story.append(Paragraph(section.title, heading))
        for paragraph in section.paragraphs:
            story.append(Paragraph(paragraph, body))
        for note in section.notes:
            story.append(Paragraph(note, body))
        if section.table is not None:
            data = [list(map(str, section.table["columns"]))] + [
                list(map(str, row)) for row in section.table["rows"]
            ]
            table = Table(data)
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), font_name),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ADB5BD")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9ECEF")),
                    ]
                )
            )
            story.append(table)
            story.append(Paragraph(section.table["caption"], body))
        if section.image is not None:
            try:
                story.append(Image(str(section.image["path"]), width=13 * cm, height=8 * cm))
                story.append(Paragraph(section.image["caption"], body))
            except (OSError, ValueError):
                story.append(Paragraph(f"[图片缺失] {section.image['caption']}", body))

    buffer = _io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    document.build(story)
    return buffer.getvalue()

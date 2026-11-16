"""工作链模板路由（034）：装配成果的保存 / 列表 / 删除；037 增加导入导出。"""
from __future__ import annotations

import json
import os
import pathlib
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response

from medsta.session.templates import TemplateStore, is_safe_name, validate_steps

router = APIRouter()


def _store(request: Request) -> TemplateStore:
    root = getattr(request.app.state, "data_root", None) or os.environ.get(
        "MEDSTA_DATA_ROOT", "data/sessions"
    )
    return TemplateStore(pathlib.Path(root))


@router.get("/templates")
def list_templates(request: Request) -> dict:
    return {"templates": _store(request).list_all()}


@router.put("/templates/{name}")
def save_template(name: str, body: dict, request: Request) -> dict:
    if not is_safe_name(name):
        raise HTTPException(
            status_code=400,
            detail="模板名只能包含中文、字母、数字、下划线与连字符（1–64 字符）",
        )
    steps = body.get("steps")
    error = validate_steps(steps)
    if error:
        raise HTTPException(status_code=400, detail=error)
    assert isinstance(steps, list)
    return _store(request).save(name, steps)


@router.delete("/templates/{name}")
def delete_template(name: str, request: Request) -> dict:
    if not is_safe_name(name):
        raise HTTPException(status_code=400, detail="非法模板名")
    if not _store(request).delete(name):
        raise HTTPException(status_code=404, detail=f"模板不存在：{name}")
    return {"ok": True}


@router.get("/templates/{name}/export")
def export_template(name: str, request: Request) -> Response:
    """导出模板为 JSON 文件（037 文件交换）。"""
    template = _store(request).load(name)
    if template is None:
        raise HTTPException(status_code=404, detail=f"模板不存在：{name}")
    payload = {
        "name": template.get("name", name),
        "steps": template.get("steps", []),
        "created_at": template.get("created_at"),
        "updated_at": template.get("updated_at"),
    }
    quoted = quote(str(payload["name"]))
    return Response(
        content=json.dumps(payload, ensure_ascii=False),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}.json"},
    )


@router.post("/templates/import")
def import_template(body: dict, request: Request, overwrite: bool = False) -> dict:
    """导入模板 JSON（037 文件交换）；重名且未 overwrite 时 409。"""
    name = str(body.get("name", "")).strip()
    steps = body.get("steps")
    if not is_safe_name(name):
        raise HTTPException(
            status_code=400,
            detail="模板名只能包含中文、字母、数字、下划线与连字符（1–64 字符）",
        )
    error = validate_steps(steps)
    if error:
        raise HTTPException(status_code=400, detail=error)
    assert isinstance(steps, list)
    store = _store(request)
    if store.load(name) is not None and not overwrite:
        raise HTTPException(
            status_code=409, detail=f"模板已存在：{name}（带 overwrite=true 覆盖）"
        )
    return store.save(name, steps)

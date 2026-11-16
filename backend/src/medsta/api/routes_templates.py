"""工作链模板路由（034）：装配成果的保存 / 列表 / 删除。"""
from __future__ import annotations

import os
import pathlib

from fastapi import APIRouter, HTTPException, Request

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
    return _store(request).save(name, steps)


@router.delete("/templates/{name}")
def delete_template(name: str, request: Request) -> dict:
    if not is_safe_name(name):
        raise HTTPException(status_code=400, detail="非法模板名")
    if not _store(request).delete(name):
        raise HTTPException(status_code=404, detail=f"模板不存在：{name}")
    return {"ok": True}

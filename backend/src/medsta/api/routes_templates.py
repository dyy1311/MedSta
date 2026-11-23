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
    # 与保存/删除同口径校验（纵深防御：路由层虽已挡住带斜杠的路径参数）
    if not is_safe_name(name):
        raise HTTPException(status_code=400, detail="非法模板名")
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


@router.get("/templates/builtin")
def list_builtin_recipes() -> dict:
    """内置推荐流程模板（按统计 skills 预设，节点均为注册表工具）。"""
    from medsta.agents.chain_recipes import recipe_catalog

    return {"recipes": recipe_catalog()}


@router.post("/sessions/{session_id}/chain/match")
async def match_chain_recipe(session_id: str, body: dict, request: Request) -> dict:
    """把推荐模板的占位槽位匹配到当前数据的真实列（AI 优先，失败回退规则匹配）。

    返回的 steps 可直接放进装配区，用户仍可修改；`warnings` 说明哪些步骤被跳过。
    """
    from starlette.concurrency import run_in_threadpool

    from medsta.session.manager import manager

    if manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    recipe_id = str(body.get("recipe_id") or "").strip()
    if not recipe_id:
        raise HTTPException(status_code=400, detail="缺少 recipe_id")
    use_ai = body.get("use_ai", True)
    try:
        return await run_in_threadpool(
            request.app.state.service.match_chain_recipe,
            session_id,
            recipe_id,
            bool(use_ai),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在") from None

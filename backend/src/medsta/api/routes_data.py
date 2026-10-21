"""数据上传 REST 路由。"""
from __future__ import annotations

import os
import pathlib
import shutil

from fastapi import APIRouter, HTTPException, Request, UploadFile

from medsta.data.parser import load_table
from medsta.data.profiler import VALID_COLUMN_TYPES, apply_column_type, profile_dataframe
from medsta.session.manager import manager

router = APIRouter()

_DEFAULT_DATA_ROOT = pathlib.Path(os.environ.get("MEDSTA_DATA_ROOT", "data/sessions"))


def _data_root(request: Request) -> pathlib.Path:
    """数据根在请求期解析：优先 app.state（测试注入），回退环境变量/默认值。"""
    configured = getattr(request.app.state, "data_root", None)
    return pathlib.Path(configured) if configured else _DEFAULT_DATA_ROOT


@router.post("/sessions/{session_id}/data")
async def upload_data(session_id: str, file: UploadFile, request: Request) -> dict:
    if manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix}")
    import uuid

    data_root = _data_root(request)
    dataset_id = uuid.uuid4().hex[:8]
    target = data_root / session_id / dataset_id / f"dataset{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    try:
        df = load_table(str(target))
    except Exception as exc:  # 解析失败必须可分类，不能冒泡成 500
        raise HTTPException(
            status_code=400,
            detail=f"数据解析失败：{type(exc).__name__}: {str(exc)[:200]}",
        ) from exc
    if df.empty and df.shape[1] == 0:
        raise HTTPException(status_code=400, detail="数据文件为空（无可解析的列）")
    profile = profile_dataframe(df)
    manager.attach_data(
        session_id,
        df=df,
        dataset_path=str(target),
        profile=profile,
        artifact_dir=data_root / session_id / dataset_id / "artifacts",
        name=file.filename or dataset_id,
        dataset_id=dataset_id,
    )
    return {
        "type": "data_profile",
        "dataset_id": dataset_id,
        "name": file.filename or dataset_id,
        "type_confirmed": False,
        "profile": profile.model_dump(),
    }


@router.patch("/sessions/{session_id}/workspace/{dataset_id}/columns")
async def patch_columns(session_id: str, dataset_id: str, body: dict) -> dict:
    """用户修正列类型（视为敲定），返回更新后的画像。"""
    session = manager.get(session_id)
    data = session.datasets.get(dataset_id) if session else None
    if data is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    column = str(body.get("column", ""))
    new_type = str(body.get("type", ""))
    if column not in data.profile.columns:
        raise HTTPException(status_code=404, detail=f"列不存在：{column}")
    if new_type not in VALID_COLUMN_TYPES:
        raise HTTPException(status_code=400, detail=f"非法列类型：{new_type}")
    apply_column_type(data.df, data.profile, column, new_type)
    data.type_confirmed = True
    data.profile.type_confirmed = True
    return {"type": "data_profile", "dataset_id": dataset_id, "profile": data.profile.model_dump()}


@router.post("/sessions/{session_id}/workspace/{dataset_id}/activate")
async def activate_workspace(session_id: str, dataset_id: str) -> dict:
    session = manager.get(session_id)
    if session is None or dataset_id not in session.datasets:
        raise HTTPException(status_code=404, detail="工作区不存在")
    data = manager.activate(session_id, dataset_id)
    return {
        "type": "data_profile",
        "dataset_id": dataset_id,
        "name": data.name,
        "type_confirmed": data.type_confirmed,
        "profile": data.profile.model_dump(),
    }

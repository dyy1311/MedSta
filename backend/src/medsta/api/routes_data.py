"""数据上传 REST 路由。"""
from __future__ import annotations

import os
import pathlib

from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from medsta.data.parser import load_table
from medsta.data.profiler import VALID_COLUMN_TYPES, apply_column_type, profile_dataframe
from medsta.errors import AppError, ErrorCode
from medsta.session.manager import manager

router = APIRouter()

_DEFAULT_DATA_ROOT = pathlib.Path(os.environ.get("MEDSTA_DATA_ROOT", "data/sessions"))
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 上传大小上限：50MB，防磁盘/内存耗尽
_COPY_CHUNK = 1024 * 1024


def _data_root(request: Request) -> pathlib.Path:
    """数据根在请求期解析：优先 app.state（测试注入），回退环境变量/默认值。"""
    configured = getattr(request.app.state, "data_root", None)
    return pathlib.Path(configured) if configured else _DEFAULT_DATA_ROOT


@router.post("/sessions/{session_id}/data")
def upload_data(session_id: str, file: UploadFile, request: Request) -> dict:
    # 同步 IO（分块写盘 + 解析 + 画像）：def 走线程池，不阻塞事件循环（P1）
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
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = file.file.read(_COPY_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过大小上限（{MAX_UPLOAD_BYTES // (1024 * 1024)}MB），请精简后重试",
                )
            out.write(chunk)
    try:
        df = load_table(str(target))
    except Exception as exc:  # 解析失败必须可分类，不能冒泡成 500
        target.unlink(missing_ok=True)  # P1：不留孤儿数据文件
        raise HTTPException(
            status_code=400,
            detail=f"数据解析失败：{type(exc).__name__}: {str(exc)[:200]}",
        ) from exc
    if df.empty and df.shape[1] == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="数据文件为空（无可解析的列）")
    # 046 行数上限：宽扁表 50MB 可达数百万行，同步画像会拖慢交互——
    # 快速拒绝优于长时间画像；上限经 MEDSTA_MAX_ROWS 可调（默认 20 万）
    try:
        max_rows = int(os.environ.get("MEDSTA_MAX_ROWS") or "200000")
    except ValueError:  # 环境变量写错不应变成 500：回退默认上限
        max_rows = 200000
    if len(df) > max_rows:
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=(
                f"数据行数 {len(df)} 超过上限 {max_rows}（环境变量 MEDSTA_MAX_ROWS 可调）；"
                "超大表会拖慢画像与交互式统计，建议先在样本上分析"
            ),
        )
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
    # REST 上传绕过 service 编排：显式落盘会话快照（032）
    request.app.state.service.persist(session_id)
    return {
        "type": "data_profile",
        "dataset_id": dataset_id,
        "name": file.filename or dataset_id,
        "type_confirmed": False,
        "profile": profile.model_dump(),
    }


@router.patch("/sessions/{session_id}/workspace/{dataset_id}/columns")
async def patch_columns(session_id: str, dataset_id: str, body: dict, request: Request) -> dict:
    """用户修正列类型（视为敲定），返回更新后的画像。

    支持批量：body 带 `types`（{列名: 类型}）时一次修改多列；
    整体校验通过后才落库，不做部分修改。

    变更同时广播 `type_confirmed`：会话区要能看到「谁把哪几列改成了什么」，
    否则工作台变了、会话区毫无记录（两端信息不同步）。
    """
    session = manager.get(session_id)
    data = session.datasets.get(dataset_id) if session else None
    if data is None:
        raise HTTPException(status_code=404, detail="工作区不存在")
    service = request.app.state.service

    types: dict = body.get("types") or {}
    if types:
        # 先整体校验再落库：任何一列/类型非法都不修改（批量原子性）
        unknown = [c for c in types if str(c) not in data.profile.columns]
        if unknown:
            raise HTTPException(
                status_code=404, detail=f"列不存在：{', '.join(map(str, unknown))}"
            )
        invalid = [t for t in types.values() if str(t) not in VALID_COLUMN_TYPES]
        if invalid:
            raise HTTPException(
                status_code=400, detail=f"非法列类型：{', '.join(map(str, invalid))}"
            )

        def _apply_batch() -> None:
            for column, new_type in types.items():
                apply_column_type(data.df, data.profile, str(column), str(new_type))
            data.type_confirmed = True
            data.profile.type_confirmed = True

        await run_in_threadpool(_apply_batch)
        service.persist(session_id)
        await service.broadcast(
            session_id,
            {
                "type": "type_confirmed",
                "dataset_id": dataset_id,
                "profile": data.profile.model_dump(),
                "updated": [str(column) for column in types],
                "source": str(body.get("source") or "manual"),
            },
        )
        return {
            "type": "data_profile",
            "dataset_id": dataset_id,
            "profile": data.profile.model_dump(),
        }

    column = str(body.get("column", ""))
    new_type = str(body.get("type", ""))
    if column not in data.profile.columns:
        raise HTTPException(status_code=404, detail=f"列不存在：{column}")
    if new_type not in VALID_COLUMN_TYPES:
        raise HTTPException(status_code=400, detail=f"非法列类型：{new_type}")

    def _apply_one() -> None:
        apply_column_type(data.df, data.profile, column, new_type)
        data.type_confirmed = True
        data.profile.type_confirmed = True

    await run_in_threadpool(_apply_one)
    service.persist(session_id)
    await service.broadcast(
        session_id,
        {
            "type": "type_confirmed",
            "dataset_id": dataset_id,
            "profile": data.profile.model_dump(),
            "updated": [column],
            "source": str(body.get("source") or "manual"),
        },
    )
    return {"type": "data_profile", "dataset_id": dataset_id, "profile": data.profile.model_dump()}


@router.delete("/sessions/{session_id}/workspace/outputs")
async def clear_workspace_outputs(session_id: str, request: Request) -> dict:
    """清空工作区既往产出（图表、统计表、执行报告），保留导入表格。"""
    try:
        return await request.app.state.service.clear_workspace_outputs(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在") from None
    except AppError as exc:
        status = 409 if exc.code == ErrorCode.SESSION_BUSY else 400
        raise HTTPException(status_code=status, detail=exc.message) from exc


@router.get("/sessions/{session_id}/workspace")
def get_workspace(session_id: str, request: Request) -> dict:
    """会话工作区快照（刷新后右栏与会话区同源；事件流轮转也能重建）。"""
    try:
        return request.app.state.service.workspace_snapshot(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="会话不存在") from None


@router.post("/sessions/{session_id}/workspace/{dataset_id}/activate")
def activate_workspace(session_id: str, dataset_id: str, request: Request) -> dict:
    session = manager.get(session_id)
    if session is None or dataset_id not in session.datasets:
        raise HTTPException(status_code=404, detail="工作区不存在")
    data = manager.activate(session_id, dataset_id)
    # 激活态也要落快照：否则重启后 active_dataset_id 回落，切换白做
    request.app.state.service.persist(session_id)
    return {
        "type": "data_profile",
        "dataset_id": dataset_id,
        "name": data.name,
        "type_confirmed": data.type_confirmed,
        "profile": data.profile.model_dump(),
    }

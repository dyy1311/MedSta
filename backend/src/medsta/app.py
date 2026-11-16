"""MedSta FastAPI 应用入口。"""
from __future__ import annotations

import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from medsta.api.routes_capabilities import router as capabilities_router
from medsta.api.routes_data import router as data_router
from medsta.api.routes_export import router as export_router
from medsta.api.routes_session import router as session_router
from medsta.api.ws import router as ws_router
from medsta.session.service import SessionService

# prod 模式前端构建产物（launcher --prod 构建后生效；dev 模式通常不存在）
FRONTEND_DIST = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "dist"

# SPA catch-all 豁免的 API/文档前缀
_API_PREFIXES = (
    "/health", "/sessions", "/data", "/ws", "/capabilities", "/export",
    "/docs", "/openapi.json", "/redoc",
)


def _build_service(data_root: pathlib.Path | None = None) -> SessionService:
    """按环境装配会话服务：模型未配置时服务可用但讨论功能返回配置提示。"""
    from agently.core.storage import LocalRecordStore

    from medsta.agents.discussion import DiscussionAgent
    from medsta.agents.interpretation import InterpretationAgent
    from medsta.config import InterpretConfig, build_gateway

    root = data_root or pathlib.Path(os.environ.get("MEDSTA_DATA_ROOT", "data/sessions"))
    record_store = LocalRecordStore(root=str(root.parent / "records"))
    interpret_config = InterpretConfig.from_env()
    try:
        gateway = build_gateway()
        agent: DiscussionAgent | None = DiscussionAgent(gateway=gateway)
        interpret_agent: InterpretationAgent | None = InterpretationAgent(gateway=gateway)
    except RuntimeError:
        agent = None
        interpret_agent = None
    return SessionService(
        record_store=record_store,
        data_root=root,
        agent=agent,
        interpret_agent=interpret_agent,
        interpret_config=interpret_config,
    )


def create_app(data_root: str | pathlib.Path | None = None) -> FastAPI:
    app = FastAPI(title="MedSta", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(session_router)
    app.include_router(data_router)
    app.include_router(capabilities_router)
    app.include_router(export_router)
    app.include_router(ws_router)

    root = pathlib.Path(data_root or os.environ.get("MEDSTA_DATA_ROOT", "data/sessions"))
    app.state.data_root = root
    app.state.service = _build_service(root)

    root.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=str(root)), name="data")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    # prod 单端口托管：dist 存在时挂载 assets 并 catch-all 回退 index.html
    if (FRONTEND_DIST / "index.html").is_file():
        assets_dir = FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{spa_path:path}", include_in_schema=False)
        def spa_fallback(spa_path: str) -> FileResponse:
            # spa_path 不带前导斜杠，统一补齐后再做 API 前缀豁免
            if f"/{spa_path}".startswith(_API_PREFIXES):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not Found")
            # 路径穿越防护：URL 编码的 ..（%2F/%2E）会进入 spa_path，
            # 解析后的真实路径必须仍位于 dist 目录内，否则回退 SPA 入口
            candidate = (FRONTEND_DIST / spa_path).resolve()
            if (
                spa_path
                and candidate.is_file()
                and candidate.is_relative_to(FRONTEND_DIST.resolve())
            ):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    return app


app = create_app()

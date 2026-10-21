"""会话相关 REST 路由。"""
from fastapi import APIRouter

from medsta.session.manager import manager

router = APIRouter()


@router.post("/sessions")
def create_session() -> dict:
    session = manager.create_session()
    return {"session_id": session.session_id, "status": session.status.value}

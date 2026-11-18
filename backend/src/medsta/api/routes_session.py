"""会话相关 REST 路由。"""
from fastapi import APIRouter, HTTPException, Request

from medsta.session.manager import manager

router = APIRouter()


@router.post("/auth/login")
def login(body: dict, request: Request) -> dict:
    """044 多用户登录：凭据换令牌（MEDSTA_USERS 未配置时 404，匿名模式不变）。"""
    import secrets

    users = getattr(request.app.state, "medsta_users", None)
    if not users:
        raise HTTPException(status_code=404, detail="未启用多用户模式")
    username = str(body.get("username", ""))
    if users.get(username) != str(body.get("password", "")):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_urlsafe(32)
    request.app.state.user_tokens[token] = username
    return {"token": token, "username": username}


@router.post("/sessions")
def create_session(request: Request) -> dict:
    owner = getattr(request.state, "username", "local")
    session = manager.create_session(owner=owner)
    return {"session_id": session.session_id, "status": session.status.value}


@router.get("/sessions")
def list_sessions(request: Request) -> dict:
    """044：当前用户的会话列表（含重启恢复的会话）。"""
    owner = getattr(request.state, "username", "local")
    items = []
    for session in manager.list_by_owner(owner):
        items.append(
            {
                "session_id": session.session_id,
                "name": session.data.name if session.data else None,
                "status": session.status.value,
                "dataset_id": session.active_dataset_id,
            }
        )
    return {"sessions": items}

"""会话相关 REST 路由。"""
from fastapi import APIRouter, HTTPException, Request

from medsta.session.manager import manager

router = APIRouter()


@router.post("/auth/login")
def login(body: dict, request: Request) -> dict:
    """044 多用户登录：凭据换令牌（MEDSTA_USERS 未配置时 404，匿名模式不变）。

    批次11 生产加固：常数时间比较（compare_digest 防时序侧信道）+
    失败限速（同客户端 IP 60 秒窗口内 5 次失败 → 429，成功登录清零计数）。
    """
    import secrets
    import time

    users = getattr(request.app.state, "medsta_users", None)
    if not users:
        raise HTTPException(status_code=404, detail="未启用多用户模式")

    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    failures = getattr(request.app.state, "login_failures", None)
    if failures is None:
        failures = {}
        request.app.state.login_failures = failures
    record = failures.get(ip)
    if record and now - record[1] >= 60:
        failures.pop(ip, None)
        record = None
    if record and record[0] >= 5:
        raise HTTPException(status_code=429, detail="尝试过于频繁，请 1 分钟后再试")

    username = str(body.get("username", ""))
    password = str(body.get("password", ""))
    expected = users.get(username)
    # 未知用户用空占位参与比较，保持比较耗时一致
    matched = secrets.compare_digest(expected if expected is not None else "", password)
    if expected is None or not matched:
        failures[ip] = ((record[0] + 1) if record else 1, record[1] if record else now)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    failures.pop(ip, None)
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


@router.post("/sessions/cleanup_duplicates")
async def cleanup_duplicate_sessions(request: Request) -> dict:
    """批次13 批量清理重复会话：按绑定文件名分组保留最新，其余删除（仅本人会话）。"""
    owner = getattr(request.state, "username", "local")
    return await request.app.state.service.cleanup_duplicate_sessions(owner)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    """批次12 删除会话：内存状态 + 快照/事件流/产物目录一并清理（归属校验在中间件）。"""
    if manager.get(session_id) is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not await request.app.state.service.delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"deleted": session_id}

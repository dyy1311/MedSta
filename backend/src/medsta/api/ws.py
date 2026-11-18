"""WebSocket 会话端点（薄封装，逻辑在 SessionService）。

send 带锁：progress(on_step ensure_future) 与主流程可能并发写帧。
出站帧经 EventLog 注入单调 seq 并落盘（035 断线重连回放的数据源）。
任何一帧处理失败都回错误帧并保持连接：JSON 解析失败、事件字段非法、
service 穿透异常都不再整条断开，客户端始终能收到可分类的错误事件。
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from medsta.errors import AppError, ErrorCode
from medsta.session.manager import manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.websocket("/ws/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    # 038/044 鉴权：多用户模式校验会话归属（close 4403）；单令牌模式校验令牌（4401）
    medsta_users: dict | None = getattr(websocket.app.state, "medsta_users", None)
    if medsta_users:
        username = getattr(websocket.app.state, "user_tokens", {}).get(
            websocket.query_params.get("token") or ""
        )
        session_for_ws = manager.get(session_id)
        if username is None or session_for_ws is None or session_for_ws.owner != username:
            await websocket.close(code=4403, reason="无权访问该会话")
            return
    else:
        expected_token: str | None = getattr(websocket.app.state, "auth_token", None)
        if expected_token and websocket.query_params.get("token") != expected_token:
            await websocket.close(code=4401, reason="缺少或错误的访问令牌（?token=）")
            return

    service = websocket.app.state.service
    event_log = service.event_log
    send_lock = asyncio.Lock()

    async def send(message: dict) -> None:
        async with send_lock:
            frame = event_log.commit(session_id, message)
            await websocket.send_json(frame)
            logger.info("ws sent %s (seq=%s)", frame.get("type"), frame.get("seq"))

    try:
        while True:
            try:
                event = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except ValueError:
                await send(
                    AppError(
                        ErrorCode.INVALID_PARAM,
                        "消息不是合法 JSON",
                        hint="请发送 JSON 对象格式的事件",
                    ).to_event()
                )
                continue
            if not isinstance(event, dict):
                await send(
                    AppError(
                        ErrorCode.INVALID_PARAM,
                        "消息必须是 JSON 对象",
                        hint='形如 {"type": "chat", "content": "..."}',
                    ).to_event()
                )
                continue
            logger.debug("ws recv %s %s", session_id[:8], event.get("type"))

            # 035 断线重连：客户端带 last_seq 时先补发缺口帧（原帧原 seq，绕过包装）
            last_seq = event.get("last_seq")
            if event.get("type") == "resume" and isinstance(last_seq, int):
                for frame in event_log.read_after(session_id, last_seq):
                    async with send_lock:
                        await websocket.send_json(frame)

            try:
                await service.handle(session_id, event, send)
            except AppError as exc:
                await send(exc.to_event())
            except WebSocketDisconnect:
                raise
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await send(
                    AppError(
                        ErrorCode.EXECUTION_FAILED,
                        f"处理 {event.get('type')} 时发生内部错误：{type(exc).__name__}",
                        hint="请重试；若持续出现请查看后端日志",
                        detail=str(exc)[:200],
                    ).to_event()
                )
    except (WebSocketDisconnect, RuntimeError):
        # 客户端断连，或对已断开的连接写帧：正常结束会话循环
        return

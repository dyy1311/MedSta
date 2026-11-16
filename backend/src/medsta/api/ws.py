"""WebSocket 会话端点（薄封装，逻辑在 SessionService）。

send 带锁：progress(on_step ensure_future) 与主流程可能并发写帧。
任何一帧处理失败都回错误帧并保持连接：JSON 解析失败、事件字段非法、
service 穿透异常都不再整条断开，客户端始终能收到可分类的错误事件。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from medsta.errors import AppError, ErrorCode

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    service = websocket.app.state.service
    send_lock = asyncio.Lock()

    async def send(message: dict) -> None:
        async with send_lock:
            await websocket.send_json(message)
            print(f"[ws] sent {message.get('type')} ({len(str(message))} chars)", flush=True)

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
            print(f"[ws] recv {session_id[:8]} {event.get('type')}", flush=True)
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

"""WebSocket 会话端点（薄封装，逻辑在 SessionService）。

send 带锁：progress(on_step ensure_future) 与主流程可能并发写帧。
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
            event = await websocket.receive_json()
            print(f"[ws] recv {session_id[:8]} {event.get('type')}", flush=True)
            await service.handle(session_id, event, send)
            print(f"[ws] handled {event.get('type')}", flush=True)
    except WebSocketDisconnect:
        return

"""会话事件流（035）：出站帧单调 seq + 追加落盘 `events.jsonl`。

断线重连时按 `last_seq` 补发缺口帧（原帧原 seq）。落盘失败降级为仅投递
（日志缺失只影响回放完整性，不阻塞实时会话）；损坏行在读取时跳过。
"""
from __future__ import annotations

import json
import pathlib

EVENT_LOG_MAX_LINES = 2000  # 轮转：超过该行数时重写为尾部 N 行


class EventLog:
    """每会话一份事件日志：`<root>/<session_id>/events.jsonl`，一行一帧。"""

    def __init__(self, root: str | pathlib.Path) -> None:
        self._root = pathlib.Path(root)
        self._counters: dict[str, int] = {}

    def _file(self, session_id: str) -> pathlib.Path:
        return self._root / session_id / "events.jsonl"

    def _counter(self, session_id: str) -> int:
        """惰性恢复：首次访问时从落盘文件读取最大 seq（重启后续接不回退）。"""
        if session_id not in self._counters:
            maximum = 0
            path = self._file(session_id)
            if path.is_file():
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        try:
                            frame = json.loads(line)
                        except ValueError:
                            continue
                        seq = frame.get("seq")
                        if isinstance(seq, int) and seq > maximum:
                            maximum = seq
                except OSError:
                    pass
            self._counters[session_id] = maximum
        return self._counters[session_id]

    def commit(self, session_id: str, message: dict) -> dict:
        """分配 seq、落盘并返回完整帧；落盘失败静默降级（投递优先）。"""
        seq = self._counter(session_id) + 1
        self._counters[session_id] = seq
        frame = {**message, "seq": seq}
        try:
            path = self._file(session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._append_with_rotation(path, frame)
        except OSError:
            pass
        return frame

    def _append_with_rotation(self, path: pathlib.Path, frame: dict) -> None:
        """追加一帧；超过 EVENT_LOG_MAX_LINES 时重写为尾部一半（seq 内存计数器不受影响）。"""
        if path.is_file() and path.stat().st_size > 0:
            with open(path, "r", encoding="utf-8") as existing:
                lines = existing.readlines()
            lines.append(json.dumps(frame, ensure_ascii=False, default=str) + "\n")
            if len(lines) > EVENT_LOG_MAX_LINES:
                lines = lines[len(lines) // 2 :]
            with open(path, "w", encoding="utf-8") as out:
                out.writelines(lines)
        else:
            with open(path, "a", encoding="utf-8") as out:
                out.write(json.dumps(frame, ensure_ascii=False, default=str) + "\n")

    def read_after(self, session_id: str, last_seq: int) -> list[dict]:
        """读取 seq 大于 last_seq 的全部历史帧（损坏行跳过）。"""
        frames: list[dict] = []
        path = self._file(session_id)
        if not path.is_file():
            return frames
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return frames
        for line in lines:
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            seq = frame.get("seq")
            if isinstance(seq, int) and seq > last_seq:
                frames.append(frame)
        return frames

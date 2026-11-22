"""会话事件流（035）：出站帧单调 seq + 追加落盘 `events.jsonl`。

断线重连时按 `last_seq` 补发缺口帧（原帧原 seq）。落盘失败降级为仅投递
（日志缺失只影响回放完整性，不阻塞实时会话）；损坏行在读取时跳过。

IO 策略（审查修复）：常规路径只做 O(1) 追加，不再每帧全量回读+重写
整个日志；行数由内存计数器维护（首次访问时从落盘文件回填）。超过
`EVENT_LOG_MAX_LINES` 时原子轮转：尾部一半写入 tmp 后 `os.replace`，
崩溃不会截断日志。
"""
from __future__ import annotations

import json
import os
import pathlib

EVENT_LOG_MAX_LINES = 2000  # 轮转：超过该行数时保留尾部一半


class EventLog:
    """每会话一份事件日志：`<root>/<session_id>/events.jsonl`，一行一帧。"""

    def __init__(self, root: str | pathlib.Path) -> None:
        self._root = pathlib.Path(root)
        self._counters: dict[str, int] = {}
        self._line_counts: dict[str, int] = {}

    def _file(self, session_id: str) -> pathlib.Path:
        return self._root / session_id / "events.jsonl"

    def _counter(self, session_id: str) -> int:
        """惰性恢复：首次访问时从落盘文件读取最大 seq（重启后续接不回退）。"""
        if session_id not in self._counters:
            maximum = 0
            lines = 0
            path = self._file(session_id)
            if path.is_file():
                try:
                    for line in path.read_text(encoding="utf-8").splitlines():
                        try:
                            frame = json.loads(line)
                        except ValueError:
                            continue
                        lines += 1
                        seq = frame.get("seq")
                        if isinstance(seq, int) and seq > maximum:
                            maximum = seq
                except OSError:
                    pass
            self._counters[session_id] = maximum
            self._line_counts[session_id] = lines
        return self._counters[session_id]

    def commit(self, session_id: str, message: dict) -> dict:
        """分配 seq、落盘并返回完整帧；落盘失败静默降级（投递优先）。"""
        seq = self._counter(session_id) + 1
        self._counters[session_id] = seq
        frame = {**message, "seq": seq}
        try:
            path = self._file(session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as out:
                out.write(json.dumps(frame, ensure_ascii=False, default=str) + "\n")
            count = self._line_counts.get(session_id, 0) + 1
            self._line_counts[session_id] = count
            if count > EVENT_LOG_MAX_LINES:
                self._rotate(path, session_id)
        except OSError:
            pass
        return frame

    def _rotate(self, path: pathlib.Path, session_id: str) -> None:
        """原子轮转：保留尾部一半，tmp 写入后 os.replace（崩溃不截断日志）。"""
        with open(path, encoding="utf-8") as existing:
            lines = existing.readlines()
        lines = lines[len(lines) // 2 :]
        tmp = path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as out:
            out.writelines(lines)
        os.replace(tmp, path)
        self._line_counts[session_id] = len(lines)

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

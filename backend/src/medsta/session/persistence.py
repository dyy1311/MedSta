"""会话快照持久化（032）：JSON + 原子写。

只存「重建会话所需的最小状态」：数据集路径与逐列类型、方案、报告、状态机位置；
DataFrame 从已落盘的数据文件重新加载，不在快照内序列化（快照体积可控）。
持久化失败降级为内存模式：返回 False，不阻塞会话主流程。
"""
from __future__ import annotations

import json
import os
import pathlib
from typing import Any

SNAPSHOT_NAME = "snapshot.json"
SNAPSHOT_VERSION = 1


class SessionStore:
    """每会话一份快照文件：`<root>/<session_id>/snapshot.json`。"""

    def __init__(self, root: str | pathlib.Path) -> None:
        self._root = pathlib.Path(root)

    def path_for(self, session_id: str) -> pathlib.Path:
        return self._root / session_id / SNAPSHOT_NAME

    def _serialize(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    def save(self, session_id: str, payload: dict) -> bool:
        """原子写快照（临时文件 + os.replace）；失败返回 False 且不留半文件。"""
        target = self.path_for(session_id)
        tmp = target.with_suffix(".json.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(self._serialize(payload), encoding="utf-8")
            os.replace(tmp, target)
            return True
        except Exception:
            # 降级为内存模式：会话继续可用，仅失去跨重启能力
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def load_all(self) -> list[dict[str, Any]]:
        """加载全部合法快照；损坏/非法的文件跳过（B7），不抛异常。"""
        snapshots: list[dict[str, Any]] = []
        if not self._root.is_dir():
            return snapshots
        for child in sorted(self._root.iterdir()):
            path = child / SNAPSHOT_NAME
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(payload, dict) and payload.get("session_id"):
                snapshots.append(payload)
        return snapshots

    def delete(self, session_id: str) -> bool:
        """删除会话全部磁盘痕迹：快照 + 数据文件 + 事件流 + 图表产物（批次12）。"""
        import shutil

        target = self._root / session_id
        if not target.is_dir():
            return False
        shutil.rmtree(target, ignore_errors=True)
        return True

    def mtime(self, session_id: str) -> int:
        """快照修改时间（ns）；无快照返回 0。用于批量清理的「保留最新」排序（批次13）。"""
        try:
            return (self._root / session_id / "snapshot.json").stat().st_mtime_ns
        except OSError:
            return 0

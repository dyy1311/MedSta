"""会话上下文实例：按 (owner, session_id) 分层管理，支撑断点续接。

为什么需要它：模型每次只能看到「画像 + 本轮诉求」，报错后用户补充信息时，
模型不知道「已确认的工作流长什么样、哪几个节点已完成、哪个节点失败、为什么」，
只能重新出方案——这正是「一次报错全部重来」的另一半根因。

分层刻意保留 owner 维度（user → session）：当前单用户场景 owner 为 None/local，
多用户上线后无需改调用方即可隔离上下文。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NODE_PENDING = "pending"
NODE_RUNNING = "running"
NODE_DONE = "done"
NODE_FAILED = "failed"

_MAX_TURNS = 5
_MAX_NOTES = 5


@dataclass
class SessionContext:
    """一个会话的分析上下文（不含原始数据，只放可安全注入模型的最小事实）。"""

    session_id: str
    owner: str | None = None
    dataset_id: str | None = None
    dataset_name: str = ""
    row_count: int = 0
    column_count: int = 0
    plan_message: str = ""
    nodes: list[dict] = field(default_factory=list)
    node_states: dict[int, str] = field(default_factory=dict)
    node_errors: dict[int, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    turns: list[str] = field(default_factory=list)

    # ---- 写入 ----

    def describe_dataset(self, *, dataset_id: str, name: str, row_count: int, columns: int) -> None:
        self.dataset_id = dataset_id
        self.dataset_name = name
        self.row_count = row_count
        self.column_count = columns

    def set_plan(self, plan: Any, nodes: list[dict]) -> None:
        """记录已确认工作流（节点来自 plan_flow，保证与 UI 同源）。"""
        self.plan_message = str(getattr(plan, "message", "") or "")
        self.nodes = list(nodes)
        self.node_states = {
            int(node["index"]): NODE_PENDING for node in nodes if "index" in node
        }
        self.node_errors.clear()

    def mark_node(self, index: int, status: str, error: dict | None = None) -> None:
        self.node_states[int(index)] = status
        if status == NODE_FAILED and error:
            self.node_errors[int(index)] = dict(error)
        else:
            self.node_errors.pop(int(index), None)

    def add_note(self, note: str) -> None:
        text = (note or "").strip()
        if not text:
            return
        self.notes.append(text)
        del self.notes[:-_MAX_NOTES]

    def add_turn(self, request: str) -> None:
        text = (request or "").strip()
        if not text:
            return
        self.turns.append(text[:200])
        del self.turns[:-_MAX_TURNS]

    # ---- 读取 ----

    def snapshot(self, limit: int = 2000) -> str:
        """给模型的最小上下文：节点图优先，剩余预算放最近的补充说明（新→旧填充）。"""
        if not self.nodes:
            return ""
        lines = [
            f"已确认工作流（{len(self.nodes)} 个节点，数据：{self.dataset_name or self.dataset_id}"
            f"，{self.row_count} 行 × {self.column_count} 列）："
        ]
        for node in self.nodes:
            index = int(node.get("index", 0))
            state = self.node_states.get(index, NODE_PENDING)
            mark = {"done": "✓", "failed": "✗", "running": "…", "pending": "·"}.get(state, "·")
            lines.append(
                f"  {mark} [{index + 1}] {node.get('title', '')}（{node.get('method', '')}）"
                f" 目标列={node.get('target_columns', [])} 参数={node.get('params', {})}"
            )
            error = self.node_errors.get(index)
            if error:
                lines.append(f"      失败原因：{error.get('message', '')}")
        head = "\n".join(lines)
        budget = limit - len(head) - 1
        extras: list[str] = []
        for note in reversed(self.notes):
            piece = f"用户补充：{note[:100]}"
            if len(piece) + 1 > budget:
                break
            extras.insert(0, piece)
            budget -= len(piece) + 1
        if not extras and self.notes:
            # 预算极小时至少给最近一条（截断），否则模型看不到用户刚补的信息
            latest = self.notes[-1][: max(0, limit - len(head) - 8)]
            if latest:
                extras = [f"用户补充：{latest}"]
        return "\n".join([head, *extras])[:limit] if extras else head[:limit]

    def as_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "owner": self.owner,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "nodes": [
                {
                    "index": index,
                    "state": self.node_states.get(index, NODE_PENDING),
                    "error": self.node_errors.get(index),
                }
                for index in sorted(self.node_states)
            ],
            "notes": list(self.notes),
        }


class SessionContextStore:
    """按 owner 分层的上下文存储：`owner → session_id → SessionContext`。"""

    def __init__(self) -> None:
        self._by_owner: dict[str | None, dict[str, SessionContext]] = {}

    def get(self, session_id: str, owner: str | None = None) -> SessionContext:
        bucket = self._by_owner.setdefault(owner, {})
        context = bucket.get(session_id)
        if context is None:
            context = SessionContext(session_id=session_id, owner=owner)
            bucket[session_id] = context
        return context

    def find(self, session_id: str) -> SessionContext | None:
        for bucket in self._by_owner.values():
            if session_id in bucket:
                return bucket[session_id]
        return None

    def drop_session(self, session_id: str) -> None:
        for owner, bucket in list(self._by_owner.items()):
            bucket.pop(session_id, None)
            if not bucket:
                self._by_owner.pop(owner, None)

    def drop_owner(self, owner: str | None) -> None:
        self._by_owner.pop(owner, None)

    def clear(self) -> None:
        self._by_owner.clear()

    def __len__(self) -> int:
        return sum(len(bucket) for bucket in self._by_owner.values())

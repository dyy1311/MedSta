"""会话状态机（宿主确定性状态，非模型决策）。

状态流转：discussing → plan_confirmed → executing → delivered →（修正）→ discussing
"""
from __future__ import annotations

import pathlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict

import pandas as pd

from medsta.data.profiler import TableProfile


class SessionStatus(str, Enum):
    DISCUSSING = "discussing"
    PLAN_CONFIRMED = "plan_confirmed"
    EXECUTING = "executing"
    DELIVERED = "delivered"


@dataclass
class SessionData:
    df: pd.DataFrame
    dataset_path: str
    profile: TableProfile
    artifact_dir: pathlib.Path
    name: str = ""
    type_confirmed: bool = False


@dataclass
class Session:
    session_id: str
    status: SessionStatus = SessionStatus.DISCUSSING
    datasets: dict = field(default_factory=dict)  # dataset_id -> SessionData
    active_dataset_id: str | None = None
    plan: object | None = None
    messages: list = field(default_factory=list)

    @property
    def data(self) -> SessionData | None:
        if self.active_dataset_id is None:
            return next(iter(self.datasets.values()), None)
        return self.datasets.get(self.active_dataset_id)


class SessionManager:
    """管理会话创建、数据挂载与状态流转。内存实现；持久化由 storage/records 负责。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}

    def create_session(self) -> Session:
        session = Session(session_id=uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def attach_data(
        self,
        session_id: str,
        *,
        df: pd.DataFrame,
        dataset_path: str,
        profile: TableProfile,
        artifact_dir: pathlib.Path,
        name: str = "",
        dataset_id: str | None = None,
    ) -> str:
        """挂载一个数据集工作区，返回 dataset_id（不覆盖已有工作区）。"""
        import uuid

        session = self._sessions[session_id]
        dataset_id = dataset_id or uuid.uuid4().hex[:8]
        session.datasets[dataset_id] = SessionData(
            df=df,
            dataset_path=dataset_path,
            profile=profile,
            artifact_dir=artifact_dir,
        )
        if session.active_dataset_id is None or dataset_id == session.active_dataset_id:
            session.active_dataset_id = dataset_id
        session.datasets[dataset_id].name = name  # type: ignore[attr-defined]
        return dataset_id

    def attach_dataset(self, session_id: str, *, df: pd.DataFrame, name: str,
                       dataset_id: str | None = None) -> str:
        """测试/快捷入口：无文件路径的内存挂载。"""
        from medsta.data.profiler import profile_dataframe

        resolved = dataset_id or uuid.uuid4().hex[:8]
        self.attach_data(
            session_id,
            df=df,
            dataset_path=name,
            profile=profile_dataframe(df),
            artifact_dir=pathlib.Path("data/sessions") / session_id / resolved / "artifacts",
            name=name,
            dataset_id=resolved,
        )
        return resolved

    def activate(self, session_id: str, dataset_id: str) -> SessionData:
        session = self._sessions[session_id]
        if dataset_id not in session.datasets:
            raise KeyError(dataset_id)
        session.active_dataset_id = dataset_id
        return session.datasets[dataset_id]

    def active_data(self, session_id: str) -> SessionData | None:
        return self._sessions[session_id].data

    def transition(self, session_id: str, status: SessionStatus) -> Session:
        session = self._sessions[session_id]
        session.status = status
        return session

    def clear(self) -> None:
        """清空全部会话（测试接缝：模块级单例需在用例间隔离）。"""
        self._sessions.clear()


manager = SessionManager()


"""会话编排服务：讨论 / 确认 / 执行 / 审阅 / 修正 / 中断 的宿主状态机接线。

错误一律转成带 code/hint 的事件，前端可分类展示；生成为后台任务，支持中断。
"""
from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import pandas as pd

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanStep, sap_status_of
from medsta.agents.flow import plan_flow
from medsta.agents.interpretation import InterpretationAgent
from medsta.config import InterpretConfig
from medsta.data.parser import load_table
from medsta.data.profiler import VALID_COLUMN_TYPES, apply_column_type, profile_dataframe
from medsta.errors import AppError, ErrorCode, ToolValidationError
from medsta.pipeline.workflow import AnalysisWorkflow
from medsta.session.manager import InvalidStateTransition, SessionStatus, manager
from medsta.session.persistence import SNAPSHOT_VERSION, SessionStore
from medsta.stats.registry import HARD_ISSUE_CODES, ToolIssue, get_tool, validate_plan

SendFn = Callable[[dict], Awaitable[None]]

# 043 输入守卫：纯问候/致谢/告别等明显闲聊，宿主直接拒绝（不调模型，零 token）
_CHITCHAT_ONLY = re.compile(
    r"^(你好|您好|hi|hello|hey|嗨|哈喽|谢谢|多谢|感谢|辛苦了|再见|拜拜|晚安|早安|"
    r"好的|收到|ok|okay|嗯+|哦+)[\s!！.。~～?？,，]*$",
    re.IGNORECASE,
)


def _looks_like_chitchat(text: str) -> bool:
    """廉价预筛：明显闲聊/无意义输入直接拒，可疑的交给模型自检。"""
    content = text.strip()
    if not content:
        return True
    if _CHITCHAT_ONLY.match(content):
        return True
    return len(content) < 2


async def _reject_chat(send: SendFn, reason: str) -> None:
    await send(
        {
            "type": "chat_rejected",
            "reason": reason or "该输入与统计分析任务无关。请描述您的统计需求"
            "（例如：比较两组疗效、检验某指标差异、分析变量相关性）。",
        }
    )

logger = logging.getLogger(__name__)

# 用户驱动的动作：记入事件流（036 消息流完整回放），帧类型为 "<event>_user"
USER_ACTION_EVENTS = {
    "chat",
    "confirm_plan",
    "review",
    "option",
    "chart_choice",
    "type_confirm",
    "run_chain",
    "plot_later",
    "interrupt",
    "retry_step",
    "amend_step",
}


def _step_signature(report: dict) -> tuple[tuple[str, str], ...]:
    """报告指纹：解释返回时用于判断报告是否已被新执行覆盖。"""
    return tuple(
        (str(step.get("method", "")), str(step.get("title", "")))
        for step in (report.get("steps") or [])
    )


class SessionService:
    def __init__(
        self,
        agent: DiscussionAgent | None = None,
        record_store: Any | None = None,
        data_root: str | pathlib.Path = "data/sessions",
        workflow_factory: Callable[[], AnalysisWorkflow] | None = None,
        interpret_agent: InterpretationAgent | None = None,
        type_advisor: Any | None = None,
        interpret_config: InterpretConfig | None = None,
        store: SessionStore | None = None,
    ) -> None:
        self._agent = agent
        if record_store is None:
            # TriggerFlow 执行需要快照存储；默认落到本地 records 目录
            from agently.core.storage import LocalRecordStore

            record_store = LocalRecordStore(
                root=str(pathlib.Path(data_root).parent / "records")
            )
        self._record_store = record_store
        self._data_root = pathlib.Path(data_root)
        self._store = store if store is not None else SessionStore(data_root)
        from medsta.session.events import EventLog

        self._event_log = EventLog(data_root)
        self._workflow_factory = workflow_factory or (
            lambda: AnalysisWorkflow(record_store=self._record_store)
        )
        self._workflows: dict[str, AnalysisWorkflow] = {}
        self._executions: dict[str, Any] = {}
        self._revision_notes: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._reports: dict[str, dict] = {}
        self._report_history: dict[str, dict[str, dict]] = {}  # session -> report_id -> report
        # 工作区清空产出后的事件 seq：刷新回放时丢掉该 seq 及更早的报告，避免旧图回魂
        self._outputs_cleared_seq: dict[str, int] = {}
        self._pending_chats: dict[str, str] = {}
        self._plans: dict[str, AnalysisPlan] = {}
        self._requests: dict[str, str] = {}
        self._busy: set[str] = set()  # 同会话任务忙标记：防 chat/答疑并发竞态
        self._interpret_agent = interpret_agent
        # 模型辅助列类型确认（041）：可注入替身；生产由 app 按 LLM 配置构建
        self._type_advisor = type_advisor
        self._interpret_config = interpret_config or InterpretConfig.from_env()
        self._interpret_tasks: dict[str, asyncio.Task] = {}
        # 在线连接注册表（原始帧发送器）：REST 触发的状态变更也要推给已连接的前端，
        # 否则「工作台改了类型、会话区没有记录」，两端信息不同步
        self._senders: dict[str, set[Any]] = {}
        # 会话上下文（owner → session 分层）：支撑报错后的断点续接与多用户隔离
        from medsta.session.context import SessionContextStore

        self._contexts = SessionContextStore()

    # ---- 会话上下文（分层实例） ----

    def _remember_plan(self, session_id: str, session: Any, plan: Any, request: str) -> None:
        """记录已确认工作流与用户诉求：后续报错/补充时模型能看到「图 + 进度 + 原因」。"""
        context = self._contexts.get(session_id, getattr(session, "owner", None))
        data = getattr(session, "data", None)
        if data is not None:
            context.describe_dataset(
                dataset_id=str(session.active_dataset_id or ""),
                name=str(getattr(data, "name", "") or ""),
                row_count=int(data.profile.row_count),
                columns=int(data.profile.column_count),
            )
        context.set_plan(plan, plan_flow(plan)["nodes"])
        context.add_turn(request)

    def _mark_node(self, session_id: str, index: int, status: str, error: dict | None) -> None:
        context = self._contexts.find(session_id)
        if context is not None:
            context.mark_node(index, status, error)

    # ---- 在线连接（REST 触发的广播出口） ----

    def attach_sender(self, session_id: str, sender: Any) -> None:
        self._senders.setdefault(session_id, set()).add(sender)

    def detach_sender(self, session_id: str, sender: Any) -> None:
        senders = self._senders.get(session_id)
        if senders is None:
            return
        senders.discard(sender)
        if not senders:
            self._senders.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict) -> dict:
        """分配 seq 并推给该会话的所有在线连接（无连接时只落事件流，供 resume 补发）。"""
        frame = self._event_log.commit(session_id, message)
        for sender in list(self._senders.get(session_id, ())):
            try:
                await sender(frame)
            except Exception:  # 连接已断开：摘除，不影响其余接收方
                self.detach_sender(session_id, sender)
        return frame

    # ---- 装配与会话 ----

    def set_agent(self, agent: DiscussionAgent | None) -> None:
        self._agent = agent

    def set_interpret_agent(
        self,
        agent: InterpretationAgent | None,
        config: InterpretConfig | None = None,
    ) -> None:
        self._interpret_agent = agent
        if config is not None:
            self._interpret_config = config

    def create_session(self, owner: str = "local") -> str:
        return manager.create_session(owner=owner).session_id

    def attach_dataframe(self, session_id: str, *, df: pd.DataFrame, dataset_path: str,
                         name: str = "") -> str:
        import uuid

        profile = profile_dataframe(df)
        dataset_id = uuid.uuid4().hex[:8]
        manager.attach_data(
            session_id,
            df=df,
            dataset_path=dataset_path,
            profile=profile,
            artifact_dir=self._data_root / session_id / dataset_id / "artifacts",
            name=name or dataset_id,
            dataset_id=dataset_id,
        )
        self._persist(session_id)
        return dataset_id

    # ---- 会话持久化（032）----

    def _build_snapshot(self, session_id: str, session: Any) -> dict:
        """组装会话快照：只含重建所需最小状态，不含 DataFrame 数据。"""
        import datetime

        datasets = []
        for ds_id, data in session.datasets.items():
            datasets.append(
                {
                    "id": ds_id,
                    "name": data.name,
                    "path": data.dataset_path,
                    "type_confirmed": data.type_confirmed,
                    "column_types": {
                        name: col.type
                        for name, col in data.profile.columns.items()
                        if col.type
                    },
                }
            )
        return {
            "version": SNAPSHOT_VERSION,
            "session_id": session_id,
            "owner": getattr(session, "owner", "local"),
            "status": session.status.value,
            "active_dataset_id": session.active_dataset_id,
            "datasets": datasets,
            "plan": (
                session.plan.model_dump() if isinstance(session.plan, AnalysisPlan) else None
            ),
            "report": self._reports.get(session_id),
            "outputs_cleared_seq": self._outputs_cleared_seq.get(session_id),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }

    def _persist(self, session_id: str) -> None:
        """关键节点落盘会话快照；失败降级内存模式（不阻塞主流程）。"""
        if self._store is None:
            return
        session = manager.get(session_id)
        if session is None:
            return
        self._store.save(session_id, self._build_snapshot(session_id, session))

    def persist(self, session_id: str) -> None:
        """公共落盘入口：供绕过 service 的 REST 路由（上传/列类型）调用。"""
        self._persist(session_id)

    def workspace_snapshot(self, session_id: str) -> dict:
        """会话工作区快照：数据集画像 + 激活项 + 当前报告。

        刷新后的右栏不能只靠 WS 事件流重建（事件流会轮转、data_profile 可能已被裁掉），
        否则「左栏有执行变动、右栏空白」。前端进入会话时先取此快照，再用回放做增量。
        """
        session = manager.get(session_id)
        if session is None:
            raise KeyError(session_id)
        datasets = [
            {
                "dataset_id": dataset_id,
                "name": data.name or dataset_id,
                "profile": data.profile.model_dump(),
                "type_confirmed": bool(getattr(data, "type_confirmed", False)),
                "active": dataset_id == session.active_dataset_id,
            }
            for dataset_id, data in session.datasets.items()
        ]
        report = self._reports.get(session_id)
        plan = self._plans.get(session_id)
        if report is not None and isinstance(plan, AnalysisPlan):
            self._stamp_plot_style(report, plan)
        return {
            "session_id": session_id,
            "status": session.status.value,
            "active_dataset_id": session.active_dataset_id,
            "datasets": datasets,
            "report": report,
            "report_id": (report or {}).get("report_id"),
            "outputs_cleared_seq": self._outputs_cleared_seq.get(session_id),
        }

    @staticmethod
    def _stamp_plot_style(report: dict, plan: AnalysisPlan) -> None:
        """把出图标注从方案 params 抄到报告步骤，刷新后前端才能回填。"""
        from medsta.stats.plotting import style_from_params

        steps = report.get("steps") or []
        for index, plan_step in enumerate(plan.steps):
            if index >= len(steps):
                break
            report_method = steps[index].get("method")
            if report_method and report_method != plan_step.method:
                continue
            steps[index]["chart_type"] = plan_step.chart_type
            steps[index]["plot_style"] = style_from_params(plan_step.params)

    def _wipe_output_artifacts(self, session: Any) -> None:
        """删除图表等执行产物文件，不碰任何数据集表文件。

        插补/清洗 CSV 写在源表的 artifacts 目录里，且 dataset_path 指向它；
        只删「不是任何数据集路径」的文件，导入表与派生表都还在。
        """
        protected: set[pathlib.Path] = set()
        for data in session.datasets.values():
            try:
                protected.add(pathlib.Path(data.dataset_path).resolve())
            except OSError:
                continue
        for data in session.datasets.values():
            folder = pathlib.Path(data.artifact_dir)
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                if not path.is_file():
                    continue
                try:
                    resolved = path.resolve()
                except OSError:
                    continue
                if resolved in protected:
                    continue
                path.unlink(missing_ok=True)

    async def clear_workspace_outputs(self, session_id: str) -> dict:
        """清空本会话工作区的统计表、图表与执行报告，保留导入及派生表格。"""
        session = manager.get(session_id)
        if session is None:
            raise KeyError(session_id)
        running = self._tasks.get(session_id)
        if (
            session.status == SessionStatus.EXECUTING
            or session_id in self._busy
            or (running is not None and not running.done())
        ):
            raise AppError(
                ErrorCode.SESSION_BUSY,
                "分析正在执行，请等待结束后再清空产出",
                hint="执行完成或中断后再清空，以免删掉正在写入的图表",
            )
        self._cancel_interpretation(session_id)
        self._reports.pop(session_id, None)
        self._report_history.pop(session_id, None)
        self._wipe_output_artifacts(session)
        frame = await self.broadcast(session_id, {"type": "workspace_outputs_cleared"})
        seq = frame.get("seq")
        if isinstance(seq, int):
            self._outputs_cleared_seq[session_id] = seq
        self._persist(session_id)
        return {
            "session_id": session_id,
            "outputs_cleared_seq": self._outputs_cleared_seq.get(session_id),
        }

    async def delete_session(self, session_id: str) -> bool:
        """删除会话：取消后台任务/工作流，移除内存状态与磁盘痕迹（批次12）。"""
        if manager.get(session_id) is None:
            return False
        self._cancel_background_task(session_id)
        self._cancel_interpretation(session_id)
        workflow = self._workflows.pop(session_id, None)
        execution = self._executions.pop(session_id, None)
        if workflow is not None and execution is not None:
            try:
                await workflow.cancel(execution, reason="session deleted")
            except Exception:
                pass
        # 会话级旁路状态一并清空：否则删除后这些条目随进程常驻（内存泄漏），
        # 且 pending_chats/requests 残留可能被同 id 的新会话误用
        self._plans.pop(session_id, None)
        self._reports.pop(session_id, None)
        self._report_history.pop(session_id, None)
        self._outputs_cleared_seq.pop(session_id, None)
        self._revision_notes.pop(session_id, None)
        self._pending_chats.pop(session_id, None)
        self._requests.pop(session_id, None)
        self._busy.discard(session_id)
        self._tasks.pop(session_id, None)
        self._interpret_tasks.pop(session_id, None)
        self._contexts.drop_session(session_id)
        manager.delete(session_id)
        if self._store is not None:
            self._store.delete(session_id)
        return True

    async def cleanup_duplicate_sessions(self, owner: str = "local") -> dict:
        """批量清理重复会话（批次13）：按绑定数据集名分组，保留每组最新（快照 mtime），
        其余删除；未绑定与执行中的会话跳过。仅作用于该 owner 的会话。"""
        groups: dict[str, list] = {}
        for session in manager.list_by_owner(owner):
            if session.data is None:
                continue  # 未绑定数据：不参与分组，避免误删空会话
            groups.setdefault(session.data.name, []).append(session)

        def _age(session: Any) -> int:
            return self._store.mtime(session.session_id) if self._store is not None else 0

        deleted: list[str] = []
        kept: list[str] = []
        skipped: list[str] = []
        for members in groups.values():
            members.sort(key=_age, reverse=True)  # 新 → 旧
            kept.append(members[0].session_id)
            for stale in members[1:]:
                if stale.status == SessionStatus.EXECUTING:
                    skipped.append(stale.session_id)  # 执行中的会话不杀
                    continue
                if await self.delete_session(stale.session_id):
                    deleted.append(stale.session_id)
                else:
                    skipped.append(stale.session_id)
        return {"deleted": deleted, "kept": kept, "skipped": skipped}

    def restore_all(self) -> int:
        """启动时从快照恢复会话；返回恢复数。

        `executing` 是未完成的执行，恢复一律降级为 `discussing`（B8）；
        单个会话恢复失败不拖垮启动。
        """
        if self._store is None:
            return 0
        restored = 0
        for snapshot in self._store.load_all():
            session_id = str(snapshot["session_id"])
            if manager.get(session_id) is not None:
                continue
            try:
                status_value = str(snapshot.get("status", "discussing"))
                if status_value == SessionStatus.EXECUTING.value:
                    status_value = SessionStatus.DISCUSSING.value
                session = manager.create_session(
                    session_id=session_id, owner=str(snapshot.get("owner", "local"))
                )
                session.status = SessionStatus(status_value)  # 恢复不走转移表
                for entry in snapshot.get("datasets") or []:
                    df = load_table(str(entry["path"]))
                    profile = profile_dataframe(df)
                    dataset_id = manager.attach_data(
                        session_id,
                        df=df,
                        dataset_path=str(entry["path"]),
                        profile=profile,
                        artifact_dir=self._data_root
                        / session_id
                        / str(entry["id"])
                        / "artifacts",
                        name=str(entry.get("name") or entry["id"]),
                        dataset_id=str(entry["id"]),
                    )
                    data = session.datasets[dataset_id]
                    for column, new_type in (entry.get("column_types") or {}).items():
                        if str(new_type) not in VALID_COLUMN_TYPES:
                            continue
                        try:
                            apply_column_type(data.df, data.profile, str(column), str(new_type))
                        except (KeyError, ValueError):
                            continue
                    data.type_confirmed = bool(entry.get("type_confirmed"))
                    data.profile.type_confirmed = data.type_confirmed
                active = snapshot.get("active_dataset_id")
                session.active_dataset_id = (
                    str(active) if active in session.datasets else next(iter(session.datasets), None)
                )
                plan_payload = snapshot.get("plan")
                if plan_payload:
                    session.plan = AnalysisPlan.model_validate(plan_payload)
                    self._plans[session_id] = session.plan
                report = snapshot.get("report")
                if report:
                    self._reports[session_id] = report
                    report_id = str(report.get("report_id") or uuid.uuid4().hex[:8])
                    report["report_id"] = report_id
                    self._report_history.setdefault(session_id, {})[report_id] = report
                cleared_seq = snapshot.get("outputs_cleared_seq")
                if isinstance(cleared_seq, int):
                    self._outputs_cleared_seq[session_id] = cleared_seq
                restored += 1
            except Exception:
                continue
        return restored

    @property
    def reports(self) -> dict[str, dict]:
        return self._reports

    @property
    def report_history(self) -> dict[str, dict[str, dict]]:
        return self._report_history

    @property
    def plans(self) -> dict[str, AnalysisPlan]:
        return self._plans

    @property
    def event_log(self):
        """事件流日志（035 断线重连回放的数据源）。"""
        return self._event_log

    def set_column_type(
        self, session_id: str, dataset_id: str, column: str, new_type: str
    ) -> dict:
        '''用户修正列类型（视为敲定），返回更新后的画像。'''
        session = manager.get(session_id)
        data = session.datasets.get(dataset_id) if session else None
        if data is None:
            raise KeyError(f"工作区不存在: {dataset_id}")
        if new_type not in VALID_COLUMN_TYPES:
            raise ValueError(f"非法列类型: {new_type}")
        apply_column_type(data.df, data.profile, column, new_type)
        data.type_confirmed = True
        self._persist(session_id)
        return data.profile.model_dump()

    def get_status(self, session_id: str) -> str:
        session = manager.get(session_id)
        assert session is not None
        return session.status.value

    async def wait_idle(self, session_id: str) -> None:
        """等待该会话的后台任务（生成 / 答疑 / 解释）结束（测试与关停时使用）。"""
        tasks = [self._tasks.get(session_id), self._interpret_tasks.get(session_id)]
        for task in tasks:
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass

    # ---- 消息编排 ----

    async def handle(self, session_id: str, event: dict, send: SendFn) -> None:
        if manager.get(session_id) is None:
            # 断线重连/历史页面可能指向已失效会话：返回可读错误而非断言崩溃
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN,
                    "会话不存在",
                    hint="刷新页面后重新创建会话",
                ).to_event()
            )
            return
        event_type = str(event.get("type") or "")
        if event_type in USER_ACTION_EVENTS:
            # 036：用户动作入事件流（占 seq、不实时广播）——刷新/重启后可重建用户气泡
            compact: dict[str, Any] = {
                "type": f"{event_type}_user",
                "content": str(event.get("content", "") or ""),
            }
            if event.get("decision"):
                compact["decision"] = str(event.get("decision"))
            if event.get("option_id"):
                compact["option_id"] = str(event.get("option_id"))
            # 047：节点级动作的定位信息要进事件流，否则回放只剩空气泡
            if event_type == "retry_step":
                compact["content"] = str(event.get("index", ""))
            elif event_type == "amend_step":
                compact["content"] = str(event.get("note") or event.get("content") or "")
                raw_index = event.get("index")
                if isinstance(raw_index, int) and not isinstance(raw_index, bool):
                    compact["index"] = raw_index
            self._event_log.commit(session_id, compact)
        handler = {
            "chat": self._on_chat,
            "confirm_plan": self._on_confirm,
            "review": self._on_review,
            "interrupt": self._on_interrupt,
            "resume": self._on_resume,
            "option": self._on_option,
            "workspace": self._on_workspace,
            "chart_choice": self._on_chart_choice,
            "type_confirm": self._on_type_confirm,
            "plot_later": self._on_plot_later,
            "run_chain": self._on_run_chain,
            "retry_step": self._on_retry_step,
            "amend_step": self._on_amend_step,
            "suggest_column_types": self._on_suggest_column_types,
        }.get(event_type)
        if handler is None:
            await send(
                AppError(
                    ErrorCode.PROTOCOL_UNSUPPORTED,
                    f"未知消息类型：{event_type}",
                    hint="检查前端协议版本，或刷新页面后重试",
                ).to_event()
            )
            return
        try:
            await handler(session_id, event, send)
        except InvalidStateTransition as exc:
            # 状态机转移守卫：协议顺序错误对客户端可见而非断连
            await send(
                AppError(
                    ErrorCode.PROTOCOL_UNSUPPORTED,
                    str(exc),
                    hint="当前会话状态不支持该操作；请刷新页面同步最新状态",
                ).to_event()
            )

    async def _on_chat(self, session_id: str, event: dict, send: SendFn) -> None:
        # 043 输入守卫（第一层，零 token）：明显闲聊直接拒绝，先于模型/数据检查
        raw_content = str(event.get("content", "") or "").strip()
        if _looks_like_chitchat(raw_content):
            await _reject_chat(send, "输入过短或为问候语。")
            return
        session = manager.get(session_id)
        assert session is not None
        if session.data is None:
            await send(
                AppError(
                    ErrorCode.DATA_REQUIRED,
                    "尚未上传数据",
                    hint="先上传 CSV/Excel，再描述分析目标",
                ).to_event()
            )
            return
        if self._agent is None:
            await send(
                AppError(
                    ErrorCode.MODEL_UNAVAILABLE,
                    "模型未配置",
                    hint="设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL（参考 .env.example）后重启",
                ).to_event()
            )
            return
        if session.data is not None and not session.data.type_confirmed:
            self._pending_chats[session_id] = str(event.get("content", ""))
            await send(
                {
                    "type": "type_review",
                    "dataset_id": session.active_dataset_id,
                    "columns": [
                        {"name": col.name, "type": col.type, "missing": col.missing}
                        for col in session.data.profile.columns.values()
                    ],
                    "message": "请先确认各列的变量类型（连续/等级/类别/索引），确认后开始讨论",
                }
            )
            return
        if session.status == SessionStatus.DELIVERED and self._interpret_agent is not None:
            # 交付态默认答疑：不产新方案，避免用户追问被误当成重规划
            await self._answer(session_id, str(event.get("content", "")), send)
            return
        if session.status not in (SessionStatus.DISCUSSING, SessionStatus.DELIVERED):
            # 执行/出图配置期不得 chat：生成新方案会降级状态机并覆盖执行中的
            # 方案，后续 review:accept 必然非法转移（P0 前门守卫）
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY,
                    "当前会话有任务进行中",
                    hint="等待任务完成，或先发送 interrupt 中断",
                ).to_event()
            )
            return
        if session_id in self._busy:
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY,
                    "当前会话有任务进行中",
                    hint="等待任务完成，或先发送 interrupt 中断",
                ).to_event()
            )
            return
        self._busy.add(session_id)
        task = asyncio.create_task(
            self._generate_plan(session_id, str(event.get("content", "")), send)
        )
        self._tasks[session_id] = task

    async def _generate_plan(self, session_id: str, content: str, send: SendFn) -> None:
        session = manager.get(session_id)
        assert session is not None and session.data is not None
        revision_note = self._revision_notes.get(session_id)

        async def on_delta(piece: str) -> None:
            await send({"type": "stream", "channel": "thinking", "delta": piece})

        try:
            await send(
                {"type": "progress", "stage": "thinking", "message": "正在结合数据画像生成分析方案…"}
            )
            plan = None
            for attempt in range(2):
                try:
                    assert self._agent is not None
                    plan = await self._agent.draft_plan_stream(
                        profile=session.data.profile,
                        user_request=content,
                        revision_note=revision_note,
                        on_delta=on_delta,
                    )
                    break
                except ToolValidationError as exc:
                    if attempt == 0:
                        feedback = "；".join(
                            f"[{i.code}] {i.message}" for i in exc.issues[:5]
                        )
                        revision_note = (
                            (revision_note + "；" if revision_note else "")
                            + f"上一次方案被拒绝：{feedback}。请修正后重新输出完整方案。"
                        )
                        continue
                    raise
            assert plan is not None
            if getattr(plan, "off_topic", False):
                # 043 输入守卫（第二层）：模型自检输入与统计任务无关——不进入方案流程
                # （phase 由前端处理 chat_rejected 帧时重置为 idle）
                await _reject_chat(
                    send,
                    str(getattr(plan, "off_topic_reason", "") or ""),
                )
                return
            session.plan = plan
            self._remember_plan(session_id, session, plan, content)
            self._requests[session_id] = content
            manager.transition(session_id, SessionStatus.DISCUSSING)
            self._persist(session_id)
            await send(
                {
                    "type": "plan",
                    "message": plan.message,
                    "steps": [step.model_dump() for step in plan.steps],
                    # 流程图：节点=现有工具、边=依赖（前端渲染成可确认的工作流图）
                    "flow": plan_flow(plan),
                    "options": [option.model_dump() for option in plan.options],
                    "estimand": plan.estimand.model_dump() if plan.estimand else None,
                    "sap_status": sap_status_of(plan),
                }
            )
            await self._record(session_id, "user_message", {"content": content})
        except asyncio.CancelledError:
            # 中断帧与状态迁移由 _on_interrupt 统一负责（单一响应方），
            # 此处只做资源清理（finally），不再补发第二帧 interrupted
            raise
        except ToolValidationError as exc:
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "模型生成的方案未通过校验",
                    "hint": "可补充说明让助手调整；常见原因：缺少必填参数或引用了不存在的列",
                    "detail": {"issues": [issue.model_dump() for issue in exc.issues]},
                }
            )
        except AppError as exc:
            await send(exc.to_event())
        except Exception as exc:  # 兜底：任何异常都要可见
            await send(
                AppError(
                    ErrorCode.EXECUTION_FAILED,
                    f"讨论流程异常：{type(exc).__name__}",
                    hint="可重试；若持续出现请查看后端日志",
                    detail=str(exc)[:300],
                ).to_event()
            )
        finally:
            self._release_task_slot(session_id)

    async def _on_confirm(self, session_id: str, event: dict, send: SendFn) -> None:
        session = manager.get(session_id)
        assert session is not None
        if not isinstance(session.plan, AnalysisPlan):
            await send(
                AppError(
                    ErrorCode.INVALID_PLAN, "尚无可用方案", hint="先讨论出方案再确认执行"
                ).to_event()
            )
            return
        chart_steps = [
            (index, step)
            for index, step in enumerate(session.plan.steps)
            if step.chart_type != "none"
        ]
        if chart_steps:
            # 出图前确认：图表类型 + 画板布局 + 显著性配置
            manager.transition(session_id, SessionStatus.PLAN_CONFIRMED)
            config_steps = []
            for index, step in chart_steps:
                spec = get_tool(step.method)
                # 该步骤允许的图表（工具注册表真相源）：前端只列可选项，
                # 避免选到本工具不支持的图（渲染失败会让用户误以为结果丢失）
                allowed = [chart for chart in (spec.charts if spec else ()) if chart != "none"]
                config_steps.append(
                    {
                        "step_id": step.step_id or f"step_{index + 1}",
                        "title": step.title,
                        "default_chart": step.chart_type,
                        "charts": allowed,
                    }
                )
            await send(
                {
                    "type": "chart_config",
                    "steps": config_steps,
                    "multi_chart": len(chart_steps) > 1,
                    "alpha": 0.05,
                    "correction": "holm",
                    "message": "出图前请确认图表类型与显著性判断标准",
                }
            )
            return
        await self._execute_plan(session_id, send)

    async def _on_chart_choice(self, session_id: str, event: dict, send: SendFn) -> None:
        session = manager.get(session_id)
        plan = session.plan if session is not None else None
        if not isinstance(plan, AnalysisPlan):
            await send(
                AppError(ErrorCode.NO_ACTIVE_RUN, "当前没有待确认的方案", hint="先讨论出方案").to_event()
            )
            return
        if not event.get("use_default"):
            overrides = {
                str(choice.get("step_id")): str(choice.get("chart_type"))
                for choice in (event.get("choices") or [])
                if isinstance(choice, dict) and choice.get("step_id") and choice.get("chart_type")
            }
            style_by_step = {
                str(choice.get("step_id")): choice
                for choice in (event.get("choices") or [])
                if isinstance(choice, dict) and choice.get("step_id")
            }
            layout = str(event.get("layout") or "separate")
            if layout not in ("separate", "shared"):
                layout = "separate"
            # 前端只能选下拉项，非法值来自协议异常/旧客户端：宿主兜底而非崩溃
            try:
                alpha = float(event.get("alpha", 0.05) or 0.05)
            except (TypeError, ValueError):
                alpha = 0.05
            alpha = min(max(alpha, 0.001), 0.2)
            correction = str(event.get("correction") or "holm").lower()
            if correction not in ("holm", "bonferroni", "none"):
                correction = "holm"
            from medsta.stats.plotting import merge_plot_style

            for index, step in enumerate(plan.steps):
                sid = step.step_id or f"step_{index + 1}"
                chosen = overrides.get(sid)
                if chosen:
                    spec = get_tool(step.method)
                    allowed = set(spec.charts) if spec is not None else set()
                    if chosen in allowed:
                        step.chart_type = chosen  # type: ignore[assignment]
                    elif step.chart_type not in allowed:
                        # 用户选择与本工具不支持的组合：降级为该工具首个可用图（无不支持则不出图）
                        alternatives = [chart for chart in (spec.charts if spec else ()) if chart != "none"]
                        step.chart_type = alternatives[0] if alternatives else "none"  # type: ignore[assignment]
                step.params["alpha"] = alpha
                step.params["correction"] = correction
                if step.chart_type != "none":
                    step.params["_layout"] = layout
                style_payload = style_by_step.get(sid)
                if isinstance(style_payload, dict):
                    merge_plot_style(step.params, style_payload)
        await self._execute_plan(session_id, send)

    async def _teardown_workflow(self, session_id: str, reason: str) -> None:
        """取消并清理会话当前的工作流与执行句柄（超时/中断路径共用）。"""
        workflow = self._workflows.pop(session_id, None)
        execution = self._executions.pop(session_id, None)
        if workflow is not None and execution is not None:
            try:
                await workflow.cancel(execution, reason=reason)
            except Exception:
                pass

    @property
    def type_advisor(self):
        """模型辅助列类型确认器（041）；测试可注入替身。"""
        return self._type_advisor

    @type_advisor.setter
    def type_advisor(self, value) -> None:
        self._type_advisor = value

    async def _on_suggest_column_types(self, session_id: str, event: dict, send: SendFn) -> None:
        """模型辅助列类型确认：宿主组装证据白名单 → 模型语义建议 → 用户采纳敲定。"""
        session = manager.get(session_id)
        if session is None or session.data is None:
            await send(
                AppError(ErrorCode.DATA_REQUIRED, "尚未上传数据", hint="先上传 CSV/Excel").to_event()
            )
            return
        advisor = self._type_advisor
        if advisor is None:
            await send(
                AppError(
                    ErrorCode.MODEL_UNAVAILABLE,
                    "模型不可用，无法提供类型建议",
                    hint="在 .env 配置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后重试",
                ).to_event()
            )
            return
        # 证据白名单：不传全量数据，仅最小必要特征
        evidence: list[dict] = []
        for name, column in session.data.profile.columns.items():
            series = session.data.df[name]
            samples = [str(value) for value in series.dropna().unique()[:5]]
            stats = {
                key: value
                for key, value in (column.stats or {}).items()
                if isinstance(value, (int, float, str))
            }
            evidence.append(
                {
                    "name": name,
                    "inferred_type": column.type,
                    "missing": column.missing,
                    "distinct": len(series.dropna().unique()),
                    "sample_values": samples,
                    "stats": stats,
                }
            )
        try:
            # 模型调用是阻塞式 HTTP（默认超时 120s），必须移出事件循环（P1）
            report = await asyncio.to_thread(advisor.advise, evidence)
        except Exception as exc:
            await send(
                AppError(
                    ErrorCode.MODEL_REQUEST_FAILED,
                    f"类型建议生成失败：{type(exc).__name__}",
                    hint="请稍后重试；若持续出现请查看后端日志",
                ).to_event()
            )
            return
        valid = [s for s in report.columns if str(s.suggested_type) in VALID_COLUMN_TYPES]
        skipped = [str(s.name) for s in report.columns if str(s.suggested_type) not in VALID_COLUMN_TYPES]
        await send(
            {
                "type": "column_type_suggestions",
                "suggestions": [s.model_dump() for s in valid],
                "skipped": skipped,
            }
        )
        await self._record(
            session_id, "column_type_suggestions", {"suggestions": [s.model_dump() for s in valid]}
        )

    async def _on_run_chain(self, session_id: str, event: dict, send: SendFn) -> None:
        """用户装配的原子工具链：宿主校验后构造手动计划执行，全程无模型参与。

        图表在装配时已选定，直接执行（跳过出图确认暂停）；
        交付态装配新链视为回到讨论态（delivered → discussing → executing）。
        """
        session = manager.get(session_id)
        if session is None or session.data is None:
            await send(
                AppError(ErrorCode.DATA_REQUIRED, "尚未上传数据", hint="先上传 CSV/Excel").to_event()
            )
            return
        if session_id in self._busy:
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY,
                    "当前会话有任务进行中",
                    hint="等待任务完成，或先发送 interrupt 中断",
                ).to_event()
            )
            return
        if session.status == SessionStatus.EXECUTING:
            # 后台执行期间新装配的链会覆盖 session.plan（状态守卫族）：
            # 执行中的会话不得再装配执行
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY,
                    "当前会话有执行进行中",
                    hint="等待审阅请求，或先发送 interrupt 中断后重新装配",
                ).to_event()
            )
            return
        raw_steps = event.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    "工作链为空",
                    hint="至少装配一个统计工具再执行",
                ).to_event()
            )
            return
        plan_steps = []
        unknown_issues = []
        for index, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                await send(
                    AppError(
                        ErrorCode.INVALID_PARAM,
                        f"步骤 {index + 1} 不是对象",
                        hint="每个步骤需包含 method/target_columns/chart_type/params",
                    ).to_event()
                )
                return
            method = str(raw.get("method", ""))
            # PlanStep.method 是 Literal 枚举：先在宿主侧校验方法名，避免 pydantic 裸错
            if get_tool(method) is None:
                unknown_issues.append(
                    ToolIssue(
                        code="TOOL_NOT_FOUND",
                        message=f"步骤 {index + 1} 引用了未知统计工具：{method}",
                        hint="从能力目录（/capabilities）中选择已登记的工具",
                        step_index=index,
                    )
                )
                continue
            plan_steps.append(
                PlanStep(
                    title=str(raw.get("title") or method or f"步骤 {index + 1}"),
                    method=cast(Any, method),  # get_tool 已校验在册
                    target_columns=[str(c) for c in (raw.get("target_columns") or [])],
                    chart_type=str(raw.get("chart_type") or "none"),  # type: ignore[arg-type]
                    params=dict(raw.get("params") or {}),
                    rationale="用户装配",
                )
            )
        if unknown_issues:
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "工作链未通过校验",
                    "hint": "检查各步骤的方法参数与目标列（详见 issues）",
                    "detail": {"issues": [issue.model_dump() for issue in unknown_issues]},
                }
            )
            return
        plan = AnalysisPlan(message="手动装配工作链", steps=plan_steps)
        issues = validate_plan(plan, session.data.df)
        hard = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]
        if hard:
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "工作链未通过校验",
                    "hint": "检查各步骤的方法参数与目标列（详见 issues）",
                    "detail": {"issues": [issue.model_dump() for issue in hard]},
                }
            )
            return
        self._busy.add(session_id)
        try:
            if session.status == SessionStatus.DELIVERED:
                manager.transition(session_id, SessionStatus.DISCUSSING)
            session.plan = plan
            self._remember_plan(session_id, session, plan, "手动装配工作链")
            await self._execute_plan(session_id, send)
        finally:
            self._busy.discard(session_id)

    def _progress_sender(self, session_id: str, send: SendFn):
        """执行进度帧发送器：工作线程回调经 ensure_future 派发回事件循环。"""

        def on_step(index: int, total: int, title: str) -> None:
            asyncio.ensure_future(
                send(
                    {
                        "type": "progress",
                        "stage": "executing",
                        "step": index + 1,
                        "total": total,
                        "title": title,
                    }
                )
            )

        return on_step

    def _step_result_sender(self, session_id: str, send: SendFn):
        """节点级交付发送器：每个节点完成即下发（失败节点也交付，不阻断后续节点）。"""

        def on_step_result(index: int, total: int, payload: dict) -> None:
            from medsta.session.context import NODE_DONE, NODE_FAILED

            self._mark_node(
                session_id,
                index,
                NODE_DONE if payload.get("status") == "success" else NODE_FAILED,
                payload.get("error"),
            )
            task = asyncio.ensure_future(
                send(
                    {
                        "type": "step_result",
                        "stage": "executing",
                        "index": index,
                        "total": total,
                        "step": payload,
                    }
                )
            )
            # 连接可能在节点交付瞬间断开：异常必须被消费，否则跨用例留下未取回的任务
            task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)

        return on_step_result

    def _cancel_background_task(self, session_id: str) -> None:
        """取消并弹出会话的后台任务（生成 / 答疑 / 执行驱动）。"""
        task = self._tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    def _release_task_slot(self, session_id: str) -> None:
        """任务收尾：仅当槽位仍属当前任务时才释放（防跨任务误清理）。

        interrupt 的取消是异步投递的：被取消的旧任务可能与新任务短暂共存。
        旧任务若无条件 pop/discard，会连新任务的登记与忙锁一起清掉——
        之后 interrupt 找不到任务（无法取消），忙锁丢失还会允许同会话
        并发生成/答疑（幻影双跑）。
        """
        current = asyncio.current_task()
        occupying = self._tasks.get(session_id)
        if occupying is not None and occupying is not current:
            return
        self._tasks.pop(session_id, None)
        self._busy.discard(session_id)

    async def _execute_plan(self, session_id: str, send: SendFn) -> None:
        logger.debug("flow _execute_plan enter %s", session_id[:8])
        session = manager.get(session_id)
        assert session is not None and session.data is not None, "执行前置条件缺失"
        plan = session.plan
        if not isinstance(plan, AnalysisPlan):
            return
        manager.transition(session_id, SessionStatus.EXECUTING)
        try:
            workflow = self._workflow_factory()
            self._workflows[session_id] = workflow
            execution = workflow.create(
                session_id=session_id,
                plan=plan,
                df=session.data.df,
                artifact_dir=session.data.artifact_dir,
                on_step=self._progress_sender(session_id, send),
                on_step_result=self._step_result_sender(session_id, send),
            )
            self._executions[session_id] = execution
            self._plans[session_id] = plan
            self._revision_notes.pop(session_id, None)
            # 后台驱动执行：WS 收包循环在计算期间保持可用（P1），
            # 审阅请求 / 失败错误 / 补图建议均经事件流异步下发
            self._tasks[session_id] = asyncio.create_task(
                self._execution_task(session_id, workflow, execution, send)
            )
        except ToolValidationError as exc:
            await self._teardown_workflow(session_id, reason="plan validation failed")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "方案参数不完整，已阻止执行",
                    "hint": "补充参数或更换方法后重试",
                    "detail": {"issues": [issue.model_dump() for issue in exc.issues]},
                }
            )
        except AppError as exc:
            await self._teardown_workflow(session_id, reason="execution app error")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(exc.to_event())
        except Exception as exc:
            await self._teardown_workflow(session_id, reason="execution failed")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                AppError(
                    ErrorCode.EXECUTION_FAILED,
                    f"执行失败：{type(exc).__name__}",
                    hint="检查数据与步骤参数；部分步骤失败会在结果卡片中标注",
                    detail=str(exc)[:300],
                ).to_event()
            )

    async def _execution_task(
        self, session_id: str, workflow: AnalysisWorkflow, execution: Any, send: SendFn
    ) -> None:
        """后台驱动执行至审阅等待：启动 → 审阅 → 报告 / 解读 / 补图建议下发。"""
        try:
            await workflow.start(execution)
            if self._executions.get(session_id) is not execution:
                return  # 中断 / 交付等入口已接管清理
            payload = await workflow.wait_for_review(execution)
            if self._executions.get(session_id) is not execution:
                return
            session = manager.get(session_id)
            plan = self._plans.get(session_id)
            if session is None or session.data is None or not isinstance(plan, AnalysisPlan):
                return
            report = payload.get("report", {})
            report_id = uuid.uuid4().hex[:8]
            report["report_id"] = report_id
            self._stamp_plot_style(report, plan)
            self._reports[session_id] = report
            self._report_history.setdefault(session_id, {})[report_id] = report
            self._persist(session_id)
            logger.debug("flow review ready %s", session_id[:8])
            await send({"type": "review_request", "report": report})
            await self._register_imputed_datasets(session_id, report, send)
            self._start_interpretation(session_id, report, session, send)
            suggestions = []
            for index, plan_step in enumerate(plan.steps):
                step_report = report["steps"][index]
                if step_report.get("table") and not step_report.get("artifact"):
                    options = self._plot_options(plan_step, session.data.df)
                    if options:
                        suggestions.append(
                            {"step_index": index, "title": plan_step.title, "charts": options}
                        )
            logger.debug(
                "flow tables=%s artifacts=%s charts=%s suggests=%s",
                [bool(s.get("table")) for s in report["steps"]],
                [s.get("artifact") for s in report["steps"]],
                [getattr(st, "chart_type", None) for st in plan.steps],
                suggestions,
            )
            if suggestions:
                await send({"type": "plot_suggest", "steps": suggestions})
        except asyncio.CancelledError:
            # 中断 / 交付 / 修正入口已响应并弹出句柄；此处后台关闭执行句柄——
            # async_close 的 _drain_pending_tasks 会等计算线程收尾，
            # 不能阻塞 WS 收包循环
            self._executions.pop(session_id, None)
            self._workflows.pop(session_id, None)
            try:
                await workflow.cancel(execution, reason="interrupted")
            except Exception:
                pass
            raise
        except ToolValidationError as exc:
            # 异常路径统一 teardown：清 workflow/execution 句柄，
            # 不留可被 review:accept 交付掉的残留执行
            await self._teardown_workflow(session_id, reason="plan validation failed")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "方案参数不完整，已阻止执行",
                    "hint": "补充参数或更换方法后重试",
                    "detail": {"issues": [issue.model_dump() for issue in exc.issues]},
                }
            )
        except AppError as exc:
            await self._teardown_workflow(session_id, reason="execution app error")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(exc.to_event())
        except TimeoutError as exc:
            if self._executions.get(session_id) is not execution:
                return  # accept/revise 已处理（句柄被弹出导致的轮询超时）
            # 审阅等待超时：必须取消工作流并清理残留执行，
            # 否则残留 interrupt 之后仍可被 review:accept 交付掉
            await self._teardown_workflow(session_id, reason="review timeout")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                AppError(
                    ErrorCode.EXECUTION_FAILED,
                    str(exc),
                    hint="请重新确认方案执行；若持续出现请查看后端日志",
                ).to_event()
            )
        except Exception as exc:
            await self._teardown_workflow(session_id, reason="execution failed")
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                AppError(
                    ErrorCode.EXECUTION_FAILED,
                    f"执行失败：{type(exc).__name__}",
                    hint="检查数据与步骤参数；部分步骤失败会在结果卡片中标注",
                    detail=str(exc)[:300],
                ).to_event()
            )
        finally:
            self._release_task_slot(session_id)

    async def _register_imputed_datasets(
        self, session_id: str, report: dict, send: SendFn
    ) -> None:
        """把数据产出型工具的产物数据集注册到会话，并通知前端追加工作区（不切换 active）。

        impute 产插补数据集（028），清洗工具产清洗数据集（045）；
        均经真实 CSV 路径与会话数据根注册。
        """
        session = manager.get(session_id)
        if session is None:
            return
        source_id = session.active_dataset_id
        for index, step in enumerate(report.get("steps") or []):
            for payload_key, imputed_flag, fallback in (
                ("imputed_dataset", True, "插补数据集"),
                ("cleaned_dataset", False, "清洗数据集"),
            ):
                payload = (step.get("result") or {}).get(payload_key)
                if not isinstance(payload, dict) or not payload.get("path"):
                    continue
                path = pathlib.Path(str(payload["path"]))
                if not path.exists():
                    logger.warning("%s missing csv %s", payload_key, path)
                    continue
                frame = pd.read_csv(path)
                name = str(payload.get("name") or f"{fallback} {index + 1}")
                # 用真实 CSV 路径与会话数据根注册（P1）：此前用数据集名当
                # dataset_path，落快照后重启恢复时 load_table 失败会拖垮整个会话
                dataset_id = uuid.uuid4().hex[:8]
                manager.attach_data(
                    session_id,
                    df=frame,
                    dataset_path=str(path),
                    profile=profile_dataframe(frame),
                    artifact_dir=self._data_root / session_id / dataset_id / "artifacts",
                    name=name,
                    dataset_id=dataset_id,
                )
                data = session.datasets.get(dataset_id)
                await send(
                    {
                        "type": "dataset_added",
                        "dataset_id": dataset_id,
                        "name": name,
                        "profile": data.profile.model_dump() if data is not None else None,
                        "imputed": imputed_flag,
                        "source_dataset_id": source_id,
                    }
                )

    # ---- 结果解释与答疑 ----

    def _start_interpretation(
        self, session_id: str, report: dict, session: Any, send: SendFn
    ) -> None:
        """后台生成解读：不阻塞 review_request，失败静默。"""
        if not self._interpret_config.enabled or self._interpret_agent is None:
            return
        plan = self._plans.get(session_id)
        data = getattr(session, "data", None)
        if not isinstance(plan, AnalysisPlan) or data is None:
            return
        signature = _step_signature(report)
        self._cancel_interpretation(session_id)
        self._interpret_tasks[session_id] = asyncio.create_task(
            self._interpret(session_id, report, plan, data.profile, signature, send)
        )

    async def _interpret(
        self,
        session_id: str,
        report: dict,
        plan: AnalysisPlan,
        profile: Any,
        signature: tuple[tuple[str, str], ...],
        send: SendFn,
    ) -> None:
        agent = self._interpret_agent
        if agent is None:
            return
        try:
            result = await asyncio.to_thread(
                agent.interpret,
                report=report,
                plan=plan,
                profile=profile,
                config=self._interpret_config,
                user_request=self._requests.get(session_id, ""),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 增强项失败不得影响交付
            logger.warning("interpret failed %s %s", session_id[:8], type(exc).__name__)
            return
        if result is None:
            logger.debug("interpret skipped %s", session_id[:8])
            return
        current = self._reports.get(session_id)
        if current is None or _step_signature(current) != signature:
            logger.debug("interpret stale dropped %s", session_id[:8])
            return
        try:
            await send({"type": "interpretation", **result.model_dump()})
            await self._record(session_id, "interpretation", result.model_dump())
        except Exception as exc:
            logger.warning("interpret send failed %s %s", session_id[:8], type(exc).__name__)

    def _cancel_interpretation(self, session_id: str) -> None:
        task = self._interpret_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _answer(self, session_id: str, question: str, send: SendFn) -> None:
        """交付态答疑：只解释已交付结果，不产新方案、不改状态。"""
        session = manager.get(session_id)
        plan = self._plans.get(session_id)
        report = self._reports.get(session_id)
        if session is None or session.data is None or report is None or not isinstance(plan, AnalysisPlan):
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN,
                    "没有可答疑的交付结果",
                    hint="先完成一次分析并交付，再针对结果提问",
                ).to_event()
            )
            return
        if session_id in self._busy:
            # 忙判定先于任何进度帧：先推「正在回答…」再回 SESSION_BUSY 会自相矛盾
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY,
                    "当前会话有任务进行中",
                    hint="等待任务完成，或先发送 interrupt 中断",
                ).to_event()
            )
            return
        await self._record(session_id, "user_message", {"content": question})
        await send({"type": "progress", "stage": "answering", "message": "正在结合交付结果回答…"})
        self._busy.add(session_id)
        self._tasks[session_id] = asyncio.create_task(
            self._answer_task(session_id, question, plan, report, session.data.profile, send)
        )

    async def _answer_task(
        self,
        session_id: str,
        question: str,
        plan: AnalysisPlan,
        report: dict,
        profile: Any,
        send: SendFn,
    ) -> None:
        agent = self._interpret_agent
        # 失败/中断/无代理路径都要释放忙锁（finally）：
        # 否则答疑一次失败后该会话永久 SESSION_BUSY，只有重启才能恢复（P0）
        try:
            if agent is None:
                return
            try:
                reply = await asyncio.to_thread(
                    agent.answer,
                    question=question,
                    report=report,
                    plan=plan,
                    profile=profile,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("answer failed %s %s", session_id[:8], type(exc).__name__)
                reply = None
            if reply is None:
                await send(
                    AppError(
                        ErrorCode.MODEL_REQUEST_FAILED,
                        "答疑暂时不可用",
                        hint="可直接提出修正意见重新分析，或稍后重试",
                    ).to_event()
                )
                return
            await send({"type": "answer", **reply.model_dump()})
            await self._record(session_id, "answer", {"question": question, **reply.model_dump()})
        finally:
            self._release_task_slot(session_id)

    @staticmethod
    def _plot_options(plan_step: Any, df: pd.DataFrame | None = None) -> list[str]:
        # 按工具支持图与列类型给默认建议（首选排最前）。
        from medsta.data.profiler import _infer_column_type
        from medsta.stats.plotting import default_chart_for
        from medsta.stats.registry import get_tool

        spec = get_tool(plan_step.method)
        if spec is None:
            return []
        preferred = ""
        if df is not None and plan_step.target_columns:
            col_type = _infer_column_type(df[plan_step.target_columns[0]], plan_step.target_columns[0], 0)
            preferred = default_chart_for(col_type, plan_step.method)
        options = [chart for chart in spec.charts if chart != "none"]
        if preferred in options:
            options.remove(preferred)
            options.insert(0, preferred)
        return options

    async def _on_review(self, session_id: str, event: dict, send: SendFn) -> None:
        workflow = self._workflows.get(session_id)
        execution = self._executions.get(session_id)
        session = manager.get(session_id)
        if (
            (workflow is None or execution is None)
            and event.get("decision") == "revise"
            and session is not None
            and session.status == SessionStatus.DELIVERED
        ):
            # 交付后「调整分析方案」：回到讨论态，后续 chat 重新生成方案
            self._cancel_interpretation(session_id)
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                {"type": "back_to_discussion", "message": "已回到方案讨论，请说明要调整的方向"}
            )
            return
        if workflow is None or execution is None:
            # 重启恢复的审阅态：报告已从快照还原，但执行句柄不在内存。
            # 此前只能重看、不能交付（点「确认交付」必撞 NO_ACTIVE_RUN）。
            # 这里属于「恢复期状态重建」，与 restore_all 同口径直接赋值、不走转移表。
            restored_report = self._reports.get(session_id)
            if (
                event.get("decision") == "accept"
                and restored_report is not None
                and session is not None
                and session.status in (SessionStatus.DISCUSSING, SessionStatus.DELIVERED)
            ):
                session.status = SessionStatus.DELIVERED
                self._persist(session_id)
                await send({"type": "delivered", "report": restored_report})
                await self._record(session_id, "delivery", {"report": restored_report})
                return
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN, "当前没有进行中的执行", hint="先确认方案并执行"
                ).to_event()
            )
            return
        decision = event.get("decision")
        if decision == "accept":
            try:
                await workflow.review(execution, {"decision": "accept"})
            except RuntimeError:
                # 计算尚未进入审阅等待（启动后立即 accept 的竞态）
                await send(
                    AppError(
                        ErrorCode.NO_ACTIVE_RUN,
                        "执行尚未完成，暂无可交付的审阅",
                        hint="待审阅请求到达后再确认交付",
                    ).to_event()
                )
                return
            report = execution.result.get_state("report")
            manager.transition(session_id, SessionStatus.DELIVERED)
            # 落盘先于送达：客户端看到 delivered 时交付态已持久化，
            # 也避免 accept 后立即断连把 persist 连同 await 链一起取消
            self._executions.pop(session_id, None)
            self._workflows.pop(session_id, None)
            self._cancel_background_task(session_id)
            self._persist(session_id)
            await send({"type": "delivered", "report": report})
            await self._record(session_id, "delivery", {"report": report})
        elif decision == "revise":
            note = str(event.get("content", "")).strip()
            if note:
                self._revision_notes[session_id] = note
            await workflow.cancel(execution, reason="revised")
            self._executions.pop(session_id, None)
            self._workflows.pop(session_id, None)
            self._cancel_background_task(session_id)
            manager.transition(session_id, SessionStatus.DISCUSSING)
            if note:
                # 有修正意见就直接接续讨论：模型据此重出方案，用户不必再手动发一条
                # （此前只回「已记录修正意见」，用户重复点提交会撞 NO_ACTIVE_RUN）
                await send(
                    {
                        "type": "back_to_discussion",
                        "message": "已记录修正意见，正在按修正重新生成方案…",
                    }
                )
                try:
                    await self._generate_plan(session_id, note, send)
                except Exception as exc:  # 模型失败：回到可继续讨论的状态
                    await send(
                        AppError(
                            ErrorCode.MODEL_REQUEST_FAILED,
                            f"按修正重新生成方案失败：{type(exc).__name__}",
                            hint="可直接再发一条说明，或检查模型配置后重试",
                            detail=str(exc)[:200],
                        ).to_event()
                    )
            else:
                await send(
                    {"type": "back_to_discussion", "message": "已记录修正意见，请继续讨论"}
                )
        else:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM, f"未知审阅决定：{decision}", hint="accept 或 revise"
                ).to_event()
            )

    async def _on_workspace(self, session_id: str, event: dict, send: SendFn) -> None:
        """切换激活工作区，并推送该数据集画像。"""
        dataset_id = str(event.get("dataset_id", ""))
        session = manager.get(session_id)
        if session is None or dataset_id not in session.datasets:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"工作区不存在：{dataset_id}",
                    hint="先上传数据，或从已有工作区列表中选择",
                ).to_event()
            )
            return
        data = manager.activate(session_id, dataset_id)
        self._persist(session_id)
        await send(
            {
                "type": "data_profile",
                "dataset_id": dataset_id,
                "name": data.name,
                "type_confirmed": data.type_confirmed,
                "profile": data.profile.model_dump(),
            }
        )

    async def _on_type_confirm(self, session_id: str, event: dict, send: SendFn) -> None:
        # 用户敲定列类型：保存 -> type_confirmed -> 自动继续 pending chat。
        session = manager.get(session_id)
        data = session.data if session else None
        if data is None:
            await send(AppError(ErrorCode.DATA_REQUIRED, "尚未上传数据").to_event())
            return
        types: dict = event.get("types") or {}
        try:
            # 先整体校验再落库：非法类型/未知列都不应造成部分列已被修改
            # （此前只预检类型，未知列在第二循环才 KeyError → 画像半更新，批次11）
            for column, new_type in types.items():
                if str(new_type) not in VALID_COLUMN_TYPES:
                    raise ValueError(f"非法列类型: {new_type}")
                if str(column) not in data.profile.columns:
                    raise KeyError(f"列不存在: {column}")
            for column, new_type in types.items():
                apply_column_type(data.df, data.profile, str(column), str(new_type))
        except KeyError as exc:
            await send(AppError(ErrorCode.COLUMN_NOT_FOUND, str(exc)).to_event())
            return
        except ValueError as exc:
            await send(AppError(ErrorCode.INVALID_PARAM, str(exc)).to_event())
            return
        data.type_confirmed = True
        data.profile.type_confirmed = True
        self._persist(session_id)
        await send(
            {
                "type": "type_confirmed",
                "dataset_id": session.active_dataset_id,  # type: ignore[union-attr]
                "profile": data.profile.model_dump(),
                "updated": [str(column) for column in types],
                "source": "type_review",
            }
        )
        content = self._pending_chats.pop(session_id, None)
        if content:
            await self._on_chat(session_id, {"type": "chat", "content": content}, send)

    async def _on_plot_later(self, session_id: str, event: dict, send: SendFn) -> None:
        # 表格型步骤补绘图：单步渲染并更新报告。
        import pathlib as _pathlib

        from medsta.stats.plotting import render_chart
        from medsta.stats.registry import get_tool

        session = manager.get(session_id)
        report = self._reports.get(session_id)
        plan = self._plans.get(session_id)
        if session is None or session.data is None or report is None or plan is None:
            await send(AppError(ErrorCode.NO_ACTIVE_RUN, "没有可补绘图的执行").to_event())
            return
        try:
            index = int(event.get("step_index", -1))
        except (TypeError, ValueError):
            index = -1
        chart_type = str(event.get("chart_type", ""))
        if not (0 <= index < len(plan.steps)):
            await send(AppError(ErrorCode.INVALID_PARAM, "步骤序号非法").to_event())
            return
        report_step = report["steps"][index] if index < len(report.get("steps") or []) else None
        method = str(
            event.get("method")
            or (report_step or {}).get("method")
            or plan.steps[index].method
        )
        spec = get_tool(method)
        if spec is None or chart_type not in spec.charts:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"该方法不支持图表 {chart_type}",
                    hint=f"可选: {', '.join(spec.charts) if spec else 'none'}",
                ).to_event()
            )
            return
        source = plan.steps[index] if plan.steps[index].method == method else next(
            (item for item in plan.steps if item.method == method), None
        )
        if source is not None:
            step = source.model_copy(update={"chart_type": chart_type})
        else:
            step = PlanStep(
                title=str((report_step or {}).get("title") or spec.title),
                method=method,  # type: ignore[arg-type]
                target_columns=[],
                chart_type=chart_type,  # type: ignore[arg-type]
                params={},
                rationale="改标注重绘",
            )
        from medsta.stats.plotting import merge_plot_style, style_from_params

        merge_plot_style(step.params, event)
        if plan.steps[index].method == method:
            plan.steps[index] = step
        # 补图必须用该节点当时看到的表：上游插补/清洗的产物不能退回原始数据
        frame = await asyncio.to_thread(
            self._input_frame,
            plan,
            session.data.df,
            session.data.artifact_dir,
            index,
        )
        path = await asyncio.to_thread(
            render_chart,
            frame,
            step,
            _pathlib.Path(session.data.artifact_dir),
            index,
            result=report["steps"][index].get("result"),
        )
        report["steps"][index]["artifact"] = path.name
        report["steps"][index]["result"]["artifact"] = path.name
        report["steps"][index]["chart_type"] = chart_type
        report["steps"][index]["plot_style"] = style_from_params(step.params)
        result_body = report["steps"][index].setdefault("result", {})
        result_body["plot_rev"] = int(result_body.get("plot_rev") or 0) + 1
        self._reports[session_id] = report
        self._persist(session_id)
        await send({"type": "review_request", "report": report, "updated": True})

    # ---- 工作链推荐模板：AI 一键匹配（宿主筛候选 + 逐步校验） ----

    def match_chain_recipe(
        self, session_id: str, recipe_id: str, use_ai: bool = True
    ) -> dict:
        """把内置模板的占位槽位匹配到当前数据的真实列（AI 优先，失败回退规则）。"""
        from medsta.agents.chain_recipes import (
            candidates_for,
            get_recipe,
            match_recipe,
        )
        from medsta.stats.registry import validate_step

        session = manager.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.data is None:
            raise ValueError("当前会话还没有数据，先上传表格")
        recipe = get_recipe(recipe_id)
        if recipe is None:
            raise ValueError(f"未知模板：{recipe_id}")

        data = session.data
        choices: dict[str, str] = {}
        ai_used = False
        if use_ai and self._agent is not None:
            candidates = {
                slot: candidates_for(data.df, data.profile, slot) for slot in recipe.slots()
            }
            try:
                choices = self._agent.match_chain_slots(
                    recipe=recipe, candidates=candidates, profile=data.profile
                )
                ai_used = bool(choices)
            except Exception as exc:  # 模型失败不影响「能载入」
                logger.warning("模板列匹配模型调用失败，回退规则匹配：%s", exc)

        result = match_recipe(recipe, data.df, data.profile, choices)

        # 逐步硬校验：候选虽合法，但组合后仍可能不满足工具约束（如 chi_square 缺列）
        steps: list[dict] = []
        warnings = list(result.warnings)
        matched: list[dict] = []
        for step in result.steps:
            from medsta.agents.discussion import PlanStep

            candidate_step = PlanStep.model_validate(step)
            issues = [
                issue
                for issue in validate_step(candidate_step, data.df)
                if issue.code in HARD_ISSUE_CODES
            ]
            if issues:
                warnings.append(
                    f"「{step['title']}」未通过校验（{issues[0].message}），已从推荐链中移除"
                )
                continue
            index = len(steps)
            steps.append(step)
            matched.extend(
                {**item, "step": index}
                for item in result.matched
                if item["step"] == result.steps.index(step)
            )

        return {
            "recipe_id": recipe.id,
            "title": recipe.title,
            "ai": ai_used,
            "steps": steps,
            "matched": matched,
            "warnings": warnings,
        }

    # ---- 047 节点级重试 / 定点修正（断点续接） ----

    def _retry_preconditions(self, session_id: str) -> tuple[Any, dict, AnalysisPlan] | None:
        """读取重试所需上下文（数据 / 报告 / 方案），缺失时返回 None。"""
        session = manager.get(session_id)
        report = self._reports.get(session_id)
        plan = self._plans.get(session_id)
        if (
            session is None
            or session.data is None
            or report is None
            or not isinstance(plan, AnalysisPlan)
        ):
            return None
        return session, report, plan

    def _input_frame(
        self, plan: AnalysisPlan, df: pd.DataFrame, artifact_dir: Any, start: int
    ) -> pd.DataFrame:
        """重放 start 之前的数据产出型节点，得到该节点应使用的表。

        非产出型节点不改变表，跳过，避免重画上游统计图、改写已交付结果。
        插补使用固定随机种子，重放与首次执行得到同一张表。
        """
        from medsta.pipeline.executor import execute_node
        from medsta.stats.registry import FRAME_METHODS

        current = df
        for index in range(start):
            step = plan.steps[index]
            if step.method not in FRAME_METHODS:
                continue
            _payload, next_frame = execute_node(current, step, artifact_dir, index)
            if next_frame is not None:
                current = next_frame
        return current

    async def _rerun_from(
        self, session_id: str, start: int, report: dict, plan: AnalysisPlan, send: SendFn
    ) -> None:
        """从 start 节点起重跑（含下游）：逐节点交付，节点失败不阻断后续。"""
        from medsta.pipeline.executor import execute_node
        from medsta.session.context import NODE_DONE, NODE_FAILED

        session = manager.get(session_id)
        assert session is not None and session.data is not None
        total = len(plan.steps)
        self._busy.add(session_id)
        try:
            artifact_dir = session.data.artifact_dir
            df = await asyncio.to_thread(
                self._input_frame, plan, session.data.df, artifact_dir, start
            )
            for index in range(start, total):
                step = plan.steps[index]
                await send(
                    {
                        "type": "progress",
                        "stage": "executing",
                        "step": index + 1,
                        "total": total,
                        "title": step.title,
                    }
                )
                payload, next_frame = await asyncio.to_thread(
                    execute_node, df, step, artifact_dir, index
                )
                if next_frame is not None:
                    df = next_frame
                self._mark_node(
                    session_id,
                    index,
                    NODE_DONE if payload.get("status") == "success" else NODE_FAILED,
                    payload.get("error"),
                )
                report["steps"][index] = payload
                self._reports[session_id] = report
                await send(
                    {
                        "type": "step_result",
                        "stage": "executing",
                        "index": index,
                        "total": total,
                        "step": {**payload, "index": index, "total": total, "updated": True},
                    }
                )
            session.plan = plan
            self._stamp_plot_style(report, plan)
            self._persist(session_id)
            await send({"type": "review_request", "report": report, "updated": True})
        finally:
            self._busy.discard(session_id)

    async def _on_retry_step(self, session_id: str, event: dict, send: SendFn) -> None:
        """重跑指定节点及其下游：报错后不必整条链重来。"""
        context = self._retry_preconditions(session_id)
        if context is None:
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN, "没有可重试的执行", hint="先确认方案并执行"
                ).to_event()
            )
            return
        if session_id in self._busy:
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY, "当前有任务在运行", hint="等待完成或中断后再重试"
                ).to_event()
            )
            return
        session, report, plan = context
        try:
            index = int(event.get("index", -1))
        except (TypeError, ValueError):
            index = -1
        if not (0 <= index < len(plan.steps)):
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"节点序号非法：{event.get('index')}",
                    hint=f"有效范围 0..{len(plan.steps) - 1}",
                ).to_event()
            )
            return
        overrides = event.get("overrides")
        if isinstance(overrides, dict) and overrides:
            update: dict = {}
            if isinstance(overrides.get("params"), dict):
                update["params"] = {**plan.steps[index].params, **overrides["params"]}
            if isinstance(overrides.get("target_columns"), list):
                update["target_columns"] = [str(c) for c in overrides["target_columns"]]
            if overrides.get("chart_type"):
                update["chart_type"] = str(overrides["chart_type"])
            if update:
                plan.steps[index] = plan.steps[index].model_copy(update=update)
                session.plan = plan
                self._plans[session_id] = plan
        issues = [
            issue
            for issue in validate_plan(plan, session.data.df)
            if issue.code in HARD_ISSUE_CODES
        ]
        if issues:
            await send(
                {
                    "type": "error",
                    "code": ErrorCode.INVALID_PLAN.value,
                    "message": "重试前校验未通过（该节点参数仍需修正）",
                    "hint": "按 issues 修改该节点参数后再重试",
                    "detail": {"issues": [issue.model_dump() for issue in issues]},
                }
            )
            return
        await self._rerun_from(session_id, index, report, plan, send)

    async def _on_amend_step(self, session_id: str, event: dict, send: SendFn) -> None:
        """用户补充信息后，让模型只重写这一个节点，再重跑该节点及下游。"""
        context = self._retry_preconditions(session_id)
        if context is None:
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN, "没有可修正的执行", hint="先确认方案并执行"
                ).to_event()
            )
            return
        if session_id in self._busy:
            await send(
                AppError(
                    ErrorCode.SESSION_BUSY, "当前有任务在运行", hint="等待完成或中断后再修正"
                ).to_event()
            )
            return
        session, report, plan = context
        if self._agent is None:
            await send(
                AppError(
                    ErrorCode.MODEL_UNAVAILABLE,
                    "模型未配置，无法按补充信息修正节点",
                    hint="配置 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 后重启；也可直接改参数重试",
                ).to_event()
            )
            return
        try:
            index = int(event.get("index", -1))
        except (TypeError, ValueError):
            index = -1
        if not (0 <= index < len(plan.steps)):
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"节点序号非法：{event.get('index')}",
                    hint=f"有效范围 0..{len(plan.steps) - 1}",
                ).to_event()
            )
            return
        note = str(event.get("note") or event.get("content") or "").strip()
        error = (report["steps"][index] or {}).get("error") or {}
        ctx = self._contexts.find(session_id)
        if ctx is not None:
            ctx.add_note(note)
        try:
            new_step = await asyncio.to_thread(
                self._agent.amend_step,
                profile=session.data.profile,
                plan=plan,
                index=index,
                error=error,
                note=note,
                context=ctx.snapshot() if ctx is not None else "",
            )
        except Exception as exc:  # 模型/校验失败：不改变现有方案
            await send(
                AppError(
                    ErrorCode.MODEL_REQUEST_FAILED,
                    f"节点修正失败：{type(exc).__name__}",
                    hint="补充更多约束（指标列名、分组列、检验方向）后重试，或直接改参数重试",
                    detail=str(exc)[:200],
                ).to_event()
            )
            return
        # 保留原节点的位置与依赖，避免修正把图结构打乱
        plan.steps[index] = new_step.model_copy(
            update={
                "depends_on": plan.steps[index].depends_on,
                "step_id": plan.steps[index].step_id,
            }
        )
        session.plan = plan
        self._plans[session_id] = plan
        self._persist(session_id)
        await send(
            {
                "type": "plan",
                "message": f"已按你的补充修正第 {index + 1} 个节点，随后重跑该节点及下游",
                "steps": [step.model_dump() for step in plan.steps],
                "flow": plan_flow(plan),
                "options": [option.model_dump() for option in plan.options],
                "estimand": plan.estimand.model_dump() if plan.estimand else None,
                "sap_status": sap_status_of(plan),
            }
        )
        await self._rerun_from(session_id, index, report, plan, send)

    async def _on_option(self, session_id: str, event: dict, send: SendFn) -> None:
        """选项式交互：confirm 执行；custom/supplement/revise/explain 回到讨论。"""
        session = manager.get(session_id)
        plan = session.plan if session is not None else None
        options = (
            {option.id: option for option in plan.options}
            if isinstance(plan, AnalysisPlan)
            else {}
        )
        option = options.get(str(event.get("option_id")))
        if option is None:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"未知选项：{event.get('option_id')}",
                    hint=f"可选选项：{', '.join(options) or '（当前无方案）'}",
                ).to_event()
            )
            return
        if option.action == "confirm":
            await self._on_confirm(session_id, event, send)
            return
        content = str(event.get("content") or "").strip()
        if not content:
            content = (
                option.description
                or f"请按选项「{option.label}」调整方案"
            )
        if option.action in ("revise", "explain"):
            content = f"（选项：{option.label}）{content}"
        await self._on_chat(session_id, {"type": "chat", "content": content}, send)

    async def _on_interrupt(self, session_id: str, event: dict, send: SendFn) -> None:
        self._cancel_interpretation(session_id)
        # 兜底释放忙锁：被取消的任务（如答疑）可能来不及走自己的 finally
        self._busy.discard(session_id)
        workflow = self._workflows.get(session_id)
        execution = self._executions.get(session_id)
        stage = "executing" if execution is not None else "thinking"
        if workflow is not None and execution is not None:
            # 句柄立即弹出保证状态一致；执行句柄的关闭交给被取消任务的
            # CancelledError 路径在后台完成——async_close 的
            # _drain_pending_tasks 会等计算线程收尾，不能阻塞 WS 收包循环
            self._executions.pop(session_id, None)
            self._workflows.pop(session_id, None)
            if self._tasks.get(session_id) is None:
                # 后台任务已自然结束（审阅等待阶段）：就地关闭暂停中的执行
                try:
                    await workflow.cancel(execution, reason="user interrupt")
                except Exception:
                    pass
        self._cancel_background_task(session_id)
        session = manager.get(session_id)
        if session is not None and session.status != SessionStatus.DELIVERED:
            manager.transition(session_id, SessionStatus.DISCUSSING)
        await send(
            {
                "type": "interrupted",
                "stage": stage,
                "message": "已中断。可继续对话调整方案，或重新执行。",
            }
        )

    async def _on_resume(self, session_id: str, event: dict, send: SendFn) -> None:
        session = manager.get(session_id)
        if session is None:
            await send(
                AppError(ErrorCode.NO_ACTIVE_RUN, "会话不存在", hint="刷新页面重新开始").to_event()
            )
            return
        execution = self._executions.get(session_id)
        workflow = self._workflows.get(session_id)
        report = self._reports.get(session_id)
        if execution is not None and report is not None and (
            workflow is None or workflow.execution_done()
        ):
            # 审阅等待：重发当前报告（重启后 executions 为空，走下方恢复分支）
            await send({"type": "resumed", "stage": "review"})
            await send({"type": "review_request", "report": report})
            return
        if session.status == SessionStatus.EXECUTING:
            # 计算进行中（含 async_start 尚未登记 _executions 的窗口）：
            # 不得降级状态机或清理工作流，否则残留 interrupt 会让
            # 后续 review:accept 撞非法转移（P0）；等待 review_request 自然到达
            await send(
                {
                    "type": "resumed",
                    "stage": "executing",
                    "message": "执行仍在进行，完成后将下发审阅请求",
                }
            )
            return
        if report is not None and session.status == SessionStatus.DELIVERED:
            # 跨重启还原交付态（032）：report 已从快照恢复
            await send({"type": "resumed", "stage": "delivered"})
            await send({"type": "delivered", "report": report})
            return
        if report is not None:
            # 报告已恢复但未交付（执行后重启）：还原审阅等待
            await send({"type": "resumed", "stage": "review"})
            await send({"type": "review_request", "report": report})
            return
        if session.status != SessionStatus.DELIVERED:
            manager.transition(session_id, SessionStatus.DISCUSSING)
        # 不附带「已回到讨论态」文案：恢复会话的 last_seq=0 全量回放已包含
        # 历史提示帧，现场再发一条会与回放重复渲染成两条相同气泡（批次11）
        await send({"type": "resumed", "stage": "discussion"})

    # ---- 记录 ----

    async def _record(self, session_id: str, kind: str, content: dict) -> None:
        """审计记录是旁路：写入失败（SQLite 锁/事件循环切换/磁盘）不得中断分析流程。

        曾经 `put` 抛 RuntimeError（Lock 绑定在另一事件循环）会冒泡到 `_on_chat`，
        把正常的讨论流程变成 EXECUTION_FAILED——记录失败与业务成败必须解耦。
        """
        if self._record_store is None:
            return
        try:
            await self._record_store.put(
                json.dumps(content, ensure_ascii=False, default=str),
                collection="sessions",
                kind=kind,
                summary=f"session {session_id} {kind}",
                scope={"session_id": session_id},
            )
        except Exception as exc:  # noqa: BLE001 - 旁路失败只留日志
            logger.warning("执行记录写入失败（不影响流程）：%s", exc)

"""会话编排服务：讨论 / 确认 / 执行 / 审阅 / 修正 / 中断 的宿主状态机接线。

错误一律转成带 code/hint 的事件，前端可分类展示；生成为后台任务，支持中断。
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import uuid
from typing import Any, Awaitable, Callable

import pandas as pd

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, sap_status_of
from medsta.agents.interpretation import InterpretationAgent
from medsta.config import InterpretConfig
from medsta.data.parser import load_table
from medsta.data.profiler import VALID_COLUMN_TYPES, apply_column_type, profile_dataframe
from medsta.errors import AppError, ErrorCode, ToolValidationError
from medsta.pipeline.workflow import AnalysisWorkflow
from medsta.session.manager import InvalidStateTransition, SessionStatus, manager
from medsta.session.persistence import SNAPSHOT_VERSION, SessionStore

SendFn = Callable[[dict], Awaitable[None]]


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
        self._workflow_factory = workflow_factory or (
            lambda: AnalysisWorkflow(record_store=self._record_store)
        )
        self._workflows: dict[str, AnalysisWorkflow] = {}
        self._executions: dict[str, Any] = {}
        self._revision_notes: dict[str, str] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._reports: dict[str, dict] = {}
        self._report_history: dict[str, dict[str, dict]] = {}  # session -> report_id -> report
        self._pending_chats: dict[str, str] = {}
        self._plans: dict[str, AnalysisPlan] = {}
        self._requests: dict[str, str] = {}
        self._busy: set[str] = set()  # 同会话任务忙标记：防 chat/答疑并发竞态
        self._interpret_agent = interpret_agent
        self._interpret_config = interpret_config or InterpretConfig.from_env()
        self._interpret_tasks: dict[str, asyncio.Task] = {}

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

    def create_session(self) -> str:
        return manager.create_session().session_id

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
            "status": session.status.value,
            "active_dataset_id": session.active_dataset_id,
            "datasets": datasets,
            "plan": (
                session.plan.model_dump() if isinstance(session.plan, AnalysisPlan) else None
            ),
            "report": self._reports.get(session_id),
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
                session = manager.create_session(session_id=session_id)
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
        event_type = event.get("type")
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
            session.plan = plan
            self._requests[session_id] = content
            manager.transition(session_id, SessionStatus.DISCUSSING)
            self._persist(session_id)
            await send(
                {
                    "type": "plan",
                    "message": plan.message,
                    "steps": [step.model_dump() for step in plan.steps],
                    "options": [option.model_dump() for option in plan.options],
                    "estimand": plan.estimand.model_dump() if plan.estimand else None,
                    "sap_status": sap_status_of(plan),
                }
            )
            await self._record(session_id, "user_message", {"content": content})
        except asyncio.CancelledError:
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                {
                    "type": "interrupted",
                    "stage": "thinking",
                    "message": "已中断生成。可以补充说明后重新讨论。",
                }
            )
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
            self._tasks.pop(session_id, None)
            self._busy.discard(session_id)

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
            await send(
                {
                    "type": "chart_config",
                    "steps": [
                        {
                            "step_id": step.step_id or f"step_{index + 1}",
                            "title": step.title,
                            "default_chart": step.chart_type,
                        }
                        for index, step in chart_steps
                    ],
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
                for choice in event.get("choices", [])
                if choice.get("step_id") and choice.get("chart_type")
            }
            layout = str(event.get("layout", "separate"))
            alpha = float(event.get("alpha", 0.05) or 0.05)
            correction = str(event.get("correction", "holm"))
            for index, step in enumerate(plan.steps):
                sid = step.step_id or f"step_{index + 1}"
                if sid in overrides:
                    step.chart_type = overrides[sid]  # type: ignore[assignment]
                step.params["alpha"] = alpha
                step.params["correction"] = correction
                if step.chart_type != "none":
                    step.params["_layout"] = layout
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

    async def _execute_plan(self, session_id: str, send: SendFn) -> None:
        print(f"[flow] _execute_plan enter {session_id[:8]}", flush=True)
        session = manager.get(session_id)
        assert session is not None
        if not isinstance(session.plan, AnalysisPlan):
            return
        manager.transition(session_id, SessionStatus.EXECUTING)
        workflow = self._workflow_factory()
        self._workflows[session_id] = workflow
        self._revision_notes.pop(session_id, None)

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

        try:
            execution = await workflow.run(
                session_id=session_id,
                plan=session.plan,
                df=session.data.df,
                artifact_dir=session.data.artifact_dir,
                on_step=on_step,
            )
            self._executions[session_id] = execution
            self._plans[session_id] = session.plan
            payload = await workflow.wait_for_review(execution)
            report = payload.get("report", {})
            report_id = uuid.uuid4().hex[:8]
            report["report_id"] = report_id
            self._reports[session_id] = report
            self._report_history.setdefault(session_id, {})[report_id] = report
            self._persist(session_id)
            print(f"[flow] review ready {session_id[:8]}", flush=True)
            await send({"type": "review_request", "report": report})
            await self._register_imputed_datasets(session_id, report, send)
            self._start_interpretation(session_id, report, session, send)
            suggestions = []
            for index, plan_step in enumerate(session.plan.steps):
                step_report = report["steps"][index]
                if step_report.get("table") and not step_report.get("artifact"):
                    options = self._plot_options(plan_step, session.data.df)
                    if options:
                        suggestions.append(
                            {"step_index": index, "title": plan_step.title, "charts": options}
                        )
            print(f"[flow] tables:", [bool(report["steps"][i].get("table")) for i in range(len(report["steps"]))],
                  "| artifacts:", [report["steps"][i].get("artifact") for i in range(len(report["steps"]))],
                  "| charts:", [getattr(st, "chart_type", None) for st in session.plan.steps],
                  "| suggests:", suggestions, flush=True)
            if suggestions:
                await send({"type": "plot_suggest", "steps": suggestions})
        except ToolValidationError as exc:
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
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(exc.to_event())
        except TimeoutError as exc:
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
            manager.transition(session_id, SessionStatus.DISCUSSING)
            await send(
                AppError(
                    ErrorCode.EXECUTION_FAILED,
                    f"执行失败：{type(exc).__name__}",
                    hint="检查数据与步骤参数；部分步骤失败会在结果卡片中标注",
                    detail=str(exc)[:300],
                ).to_event()
            )

    async def _register_imputed_datasets(
        self, session_id: str, report: dict, send: SendFn
    ) -> None:
        """把 impute 步骤产出的数据集注册到会话，并通知前端追加工作区（不切换 active）。"""
        session = manager.get(session_id)
        if session is None:
            return
        source_id = session.active_dataset_id
        for index, step in enumerate(report.get("steps") or []):
            payload = (step.get("result") or {}).get("imputed_dataset")
            if not isinstance(payload, dict) or not payload.get("path"):
                continue
            path = pathlib.Path(str(payload["path"]))
            if not path.exists():
                print(f"[impute] missing csv {path}", flush=True)
                continue
            frame = pd.read_csv(path)
            name = str(payload.get("name") or f"插补数据集 {index + 1}")
            dataset_id = manager.attach_dataset(session_id, df=frame, name=name)
            data = session.datasets.get(dataset_id)
            await send(
                {
                    "type": "dataset_added",
                    "dataset_id": dataset_id,
                    "name": name,
                    "profile": data.profile.model_dump() if data is not None else None,
                    "imputed": True,
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
            print(f"[interpret] failed {session_id[:8]} {type(exc).__name__}", flush=True)
            return
        if result is None:
            print(f"[interpret] skipped {session_id[:8]}", flush=True)
            return
        current = self._reports.get(session_id)
        if current is None or _step_signature(current) != signature:
            print(f"[interpret] stale dropped {session_id[:8]}", flush=True)
            return
        try:
            await send({"type": "interpretation", **result.model_dump()})
            await self._record(session_id, "interpretation", result.model_dump())
        except Exception as exc:
            print(f"[interpret] send failed {session_id[:8]} {type(exc).__name__}", flush=True)

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
        await self._record(session_id, "user_message", {"content": question})
        await send({"type": "progress", "stage": "answering", "message": "正在结合交付结果回答…"})
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
            print(f"[answer] failed {session_id[:8]} {type(exc).__name__}", flush=True)
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
        self._tasks.pop(session_id, None)
        self._busy.discard(session_id)

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
            await send(
                AppError(
                    ErrorCode.NO_ACTIVE_RUN, "当前没有进行中的执行", hint="先确认方案并执行"
                ).to_event()
            )
            return
        decision = event.get("decision")
        if decision == "accept":
            await workflow.review(execution, {"decision": "accept"})
            report = execution.result.get_state("report")
            manager.transition(session_id, SessionStatus.DELIVERED)
            # 落盘先于送达：客户端看到 delivered 时交付态已持久化，
            # 也避免 accept 后立即断连把 persist 连同 await 链一起取消
            self._executions.pop(session_id, None)
            self._persist(session_id)
            await send({"type": "delivered", "report": report})
            await self._record(session_id, "delivery", {"report": report})
        elif decision == "revise":
            note = str(event.get("content", "")).strip()
            if note:
                self._revision_notes[session_id] = note
            await workflow.cancel(execution, reason="revised")
            self._executions.pop(session_id, None)
            manager.transition(session_id, SessionStatus.DISCUSSING)
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
            # 先整体校验再落库：非法类型不应造成部分列已被修改
            for column, new_type in types.items():
                if str(new_type) not in VALID_COLUMN_TYPES:
                    raise ValueError(f"非法列类型: {new_type}")
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
                "dataset_id": session.active_dataset_id,
                "profile": data.profile.model_dump(),
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
        index = int(event.get("step_index", -1))
        chart_type = str(event.get("chart_type", ""))
        if not (0 <= index < len(plan.steps)):
            await send(AppError(ErrorCode.INVALID_PARAM, "步骤序号非法").to_event())
            return
        spec = get_tool(plan.steps[index].method)
        if spec is None or chart_type not in spec.charts:
            await send(
                AppError(
                    ErrorCode.INVALID_PARAM,
                    f"该方法不支持图表 {chart_type}",
                    hint=f"可选: {', '.join(spec.charts) if spec else 'none'}",
                ).to_event()
            )
            return
        step = plan.steps[index].model_copy(update={"chart_type": chart_type})
        path = render_chart(
            session.data.df,
            step,
            _pathlib.Path(session.data.artifact_dir),
            index,
            result=report["steps"][index].get("result"),
        )
        report["steps"][index]["artifact"] = path.name
        report["steps"][index]["result"]["artifact"] = path.name
        self._reports[session_id] = report
        self._persist(session_id)
        await send({"type": "review_request", "report": report, "updated": True})

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
        task = self._tasks.pop(session_id, None)
        self._cancel_interpretation(session_id)
        workflow = self._workflows.get(session_id)
        execution = self._executions.get(session_id)
        stage = "executing" if execution is not None else "thinking"
        if task is not None and not task.done():
            task.cancel()
        if workflow is not None and execution is not None:
            try:
                await workflow.cancel(execution, reason="user interrupt")
            except Exception:
                pass
            self._executions.pop(session_id, None)
            self._workflows.pop(session_id, None)
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
        report = self._reports.get(session_id)
        if execution is not None and report is not None:
            await send({"type": "resumed", "stage": "review"})
            await send({"type": "review_request", "report": report})
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
        await send(
            {
                "type": "resumed",
                "stage": "discussion",
                "message": "已回到讨论态，可继续描述分析需求。",
            }
        )

    # ---- 记录 ----

    async def _record(self, session_id: str, kind: str, content: dict) -> None:
        if self._record_store is None:
            return
        await self._record_store.put(
            json.dumps(content, ensure_ascii=False, default=str),
            collection="sessions",
            kind=kind,
            summary=f"session {session_id} {kind}",
            scope={"session_id": session_id},
        )

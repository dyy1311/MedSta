"""TriggerFlow 分析工作流：确认→执行→交付→修正回讨论。

Owner：TriggerFlow 拥有应用层编排（审阅等待、修正回边图可见）；
LocalRecordStore 拥有执行记录持久化。执行本身是宿主确定性计算（004）。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from agently import TriggerFlow
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan
from medsta.pipeline.executor import ExecutionReport, PipelineExecutor

_REVIEW_POLL_INTERVAL = 0.05
_REVIEW_TIMEOUT = 10.0
_EXECUTION_TIMEOUT = 600.0  # 同步计算的兜底上限（审阅超时不覆盖执行阶段）


class AnalysisWorkflow:
    """一次"执行→审阅→（修正循环）→交付"的编排会话。"""

    def __init__(
        self,
        executor: PipelineExecutor | None = None,
        record_store: LocalRecordStore | None = None,
    ) -> None:
        self._executor = executor or PipelineExecutor()
        self._record_store = record_store
        self._on_step = None
        self._on_step_result = None
        self._exec_done: asyncio.Event | None = None
        self._pending_start: dict = {}
        self._flow = self._build_flow()

    # ---- 图定义 ----

    def _build_flow(self) -> TriggerFlow:
        flow: Any = TriggerFlow(name="medsta-analysis")

        async def execute(data) -> dict:
            payload = data.resume if data.is_resume else data.input
            plan = AnalysisPlan.model_validate(payload["plan"])
            df: pd.DataFrame = data.require_resource("dataframe")
            artifact_dir: Path = data.require_resource("artifact_dir")
            loop = asyncio.get_running_loop()
            executor = self._executor
            business_on_step = self._on_step
            business_on_step_result = self._on_step_result

            def thread_on_step(index: int, total: int, title: str) -> None:
                # 统计计算在工作线程运行：进度回调须派发回事件循环线程
                loop.call_soon_threadsafe(self._dispatch_on_step, (index, total, title))

            def _executor_callbacks(target: Any) -> dict:
                """按 executor 签名组装回调：外部/历史替身不认识 on_step_result 时不传。"""
                import inspect

                kwargs: dict[str, Any] = {}
                params = inspect.signature(target.execute).parameters
                if business_on_step and "on_step" in params:
                    kwargs["on_step"] = thread_on_step
                if business_on_step_result and "on_step_result" in params:
                    kwargs["on_step_result"] = thread_on_step_result
                return kwargs

            def thread_on_step_result(index: int, total: int, payload: dict) -> None:
                # 节点级交付：每步完成即派发（同一线程约束）
                loop.call_soon_threadsafe(
                    self._dispatch_on_step_result, (index, total, payload)
                )

            if self._exec_done is not None:
                self._exec_done.clear()

            def run_sync() -> Any:
                return executor.execute(
                    df, plan, artifact_dir, **_executor_callbacks(executor)
                )

            report = await asyncio.to_thread(run_sync)
            if self._exec_done is not None:
                self._exec_done.set()
            dump = report.model_dump()
            await data.async_set_state("report", dump)
            return dump

        async def review(data) -> dict:
            interrupt_id = f"review-{uuid.uuid4().hex}"
            decision = await data.async_pause_for(
                type="plan_review",
                interrupt_id=interrupt_id,
                payload={"report": data.input},
                resume_to="next",
            )
            return decision

        async def route(data) -> dict:
            decision = data.input or {}
            if decision.get("decision") == "revise" and decision.get("plan"):
                await data.async_emit("RE_EXECUTE", {"plan": decision["plan"]})
            else:
                await data.async_set_state("delivered", True)
                record_store: LocalRecordStore | None = None
                try:
                    record_store = data.require_resource("record_store")
                except Exception:
                    record_store = None
                if record_store is not None:
                    session_id = data.require_resource("session_id")
                    report = data.get_state("report")
                    await record_store.put(
                        ExecutionReport.model_validate(report).model_dump_json(),
                        collection="executions",
                        kind="execution_report",
                        summary=f"session {session_id} execution report",
                        scope={"session_id": session_id},
                    )
            return decision

        flow.to(execute).to(review).to(route)
        flow.when("RE_EXECUTE").to(execute)  # 修正回边：图可见
        return flow

    # ---- 公共接口 ----

    def create(
        self,
        *,
        session_id: str,
        plan: AnalysisPlan,
        df: pd.DataFrame,
        artifact_dir: str | Path,
        on_step: Any = None,
        on_step_result: Any = None,
    ) -> Any:
        """创建执行句柄（同步、未启动）：调用方先登记句柄再后台启动。

        执行期 WS 收包不阻塞（P1）：句柄在启动前即可用于中断/清理。
        """
        self._on_step = on_step
        self._on_step_result = on_step_result
        self._exec_done = asyncio.Event()
        execution: Any = self._flow.create_execution(auto_close=False)
        execution.update_runtime_resources(
            {
                "dataframe": df,
                "artifact_dir": Path(artifact_dir),
                "session_id": session_id,
                "record_store": self._record_store,
            }
        )
        self._pending_start = {"plan": plan.model_dump()}
        return execution

    async def start(self, execution: Any) -> Any:
        """启动已创建的执行（阻塞至流程首个暂停点/完成）。"""
        return await execution.async_start(dict(self._pending_start))

    def _dispatch_on_step(self, args: tuple) -> None:
        """在事件循环线程中调用业务进度回调（工作线程经 call_soon_threadsafe 到达）。"""
        if self._on_step is not None:
            self._on_step(*args)

    def _dispatch_on_step_result(self, args: tuple) -> None:
        """节点级交付回调（同样从工作线程派发回事件循环）。"""
        if self._on_step_result is not None:
            self._on_step_result(*args)

    def execution_done(self) -> bool:
        """同步计算是否已完成（False=计算进行中；True=审阅等待或已结束）。

        供 resume 判别「执行中」与「审阅等待」：前者不得降级状态机（P0 修复）。
        """
        return self._exec_done is None or self._exec_done.is_set()

    async def run(
        self,
        *,
        session_id: str,
        plan: AnalysisPlan,
        df: pd.DataFrame,
        artifact_dir: str | Path,
        on_step: Any = None,
        on_step_result: Any = None,
    ) -> Any:
        """兼容入口：创建并启动，返回 execution 句柄（随后进入审阅等待）。"""
        execution = self.create(
            session_id=session_id,
            plan=plan,
            df=df,
            artifact_dir=artifact_dir,
            on_step=on_step,
        )
        await self.start(execution)
        return execution

    async def wait_for_review(self, execution: Any, timeout: float = _REVIEW_TIMEOUT) -> dict:
        """等待执行进入审阅等待，返回 interrupt payload（含 report）。

        超时只约束「执行完成之后」的审阅等待：同步计算期间 loop 自由，
        由独立的执行兜底上限保护，避免大计算量被误判为审阅超时。
        """
        loop = asyncio.get_running_loop()
        if self._exec_done is not None and not self._exec_done.is_set():
            await asyncio.wait_for(self._exec_done.wait(), timeout=_EXECUTION_TIMEOUT)
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            pending = execution.get_pending_interrupts()
            if pending:
                interrupt = next(iter(pending.values()))
                return interrupt.get("payload") or {}
            await asyncio.sleep(_REVIEW_POLL_INTERVAL)
        raise TimeoutError("等待审阅超时：执行未进入 plan_review 等待")

    async def cancel(self, execution: Any, reason: str = "cancelled") -> None:
        """取消执行（放弃未决审阅），用于修正回讨论。"""
        await execution.async_close(pending_interrupts="cancel", reason=reason)

    async def review(self, execution: Any, decision: dict) -> None:
        """提交审阅决定：{"decision": "accept"} 或 {"decision": "revise", "plan": {...}}。"""
        pending = execution.get_pending_interrupts()
        if not pending:
            raise RuntimeError("当前没有等待审阅的 interrupt")
        interrupt_id = next(iter(pending))
        await execution.async_continue_with(interrupt_id, decision)
        if decision.get("decision") == "accept":
            await execution.async_close()

    async def list_execution_records(self, session_id: str) -> list:
        """按会话查询执行记录（RecordRef 列表）。"""
        assert self._record_store is not None, "未配置 record_store"
        return await self._record_store.search(
            filters={"collection": "executions", "scope.session_id": session_id}
        )

"""TriggerFlow 分析工作流：确认→执行→交付→修正回讨论。

Owner：TriggerFlow 拥有应用层编排（审阅等待、修正回边图可见）；
LocalRecordStore 拥有执行记录持久化。执行本身是宿主确定性计算（004）。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pandas as pd
from agently import TriggerFlow
from agently.core.storage import LocalRecordStore
from pathlib import Path

from medsta.agents.discussion import AnalysisPlan
from medsta.pipeline.executor import ExecutionReport, PipelineExecutor

_REVIEW_POLL_INTERVAL = 0.05
_REVIEW_TIMEOUT = 10.0


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
        self._flow = self._build_flow()

    # ---- 图定义 ----

    def _build_flow(self) -> TriggerFlow:
        flow = TriggerFlow(name="medsta-analysis")
        executor = self._executor

        async def execute(data) -> dict:
            payload = data.resume if data.is_resume else data.input
            plan = AnalysisPlan.model_validate(payload["plan"])
            df: pd.DataFrame = data.require_resource("dataframe")
            artifact_dir: Path = data.require_resource("artifact_dir")
            report = executor.execute(df, plan, artifact_dir, on_step=self._on_step)
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

    async def run(
        self,
        *,
        session_id: str,
        plan: AnalysisPlan,
        df: pd.DataFrame,
        artifact_dir: str | Path,
        on_step: Any = None,
    ) -> Any:
        """启动一次工作流执行；返回 execution 句柄（随后进入审阅等待）。"""
        self._on_step = on_step
        execution = self._flow.create_execution(auto_close=False)
        execution.update_runtime_resources(
            {
                "dataframe": df,
                "artifact_dir": Path(artifact_dir),
                "session_id": session_id,
                "record_store": self._record_store,
            }
        )
        await execution.async_start({"plan": plan.model_dump()})
        return execution

    async def wait_for_review(self, execution: Any, timeout: float = _REVIEW_TIMEOUT) -> dict:
        """等待执行进入审阅等待，返回 interrupt payload（含 report）。"""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
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

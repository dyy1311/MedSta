"""005 TriggerFlow 分析工作流：run/review 公共接口测试。"""
import asyncio
import threading
import time

import pandas as pd

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.pipeline.executor import ExecutionReport, StepResult
from medsta.pipeline.workflow import AnalysisWorkflow


def _df() -> pd.DataFrame:
    return pd.DataFrame({"sales": [120.0, 135.5, 128.0, 150.0]})


def _plan(column: str = "sales") -> AnalysisPlan:
    return AnalysisPlan(
        message="方案",
        steps=[
            PlanStep(
                title="描述统计", method="describe", target_columns=[column],
                chart_type="none",
            rationale="测试依据：数值列与任务匹配", )
        ],
    )


class SlowExecutor:
    """慢执行替身：用 time.sleep 模拟秒级同步计算，验证事件循环不被阻塞。"""

    def __init__(self, delay: float = 0.05, steps: int = 4) -> None:
        self.delay = delay
        self.steps = steps
        self.execute_thread: int | None = None

    def execute(self, df, plan, artifact_dir, on_step=None) -> ExecutionReport:
        self.execute_thread = threading.get_ident()
        for index in range(self.steps):
            time.sleep(self.delay)
            if on_step is not None:
                on_step(index, self.steps, f"步骤 {index + 1}")
        return ExecutionReport(
            steps=[
                StepResult(title=f"步骤 {i + 1}", method="describe", status="success")
                for i in range(self.steps)
            ]
        )


async def _make_workflow(tmp_path, executor=None):
    from agently.core.storage import LocalRecordStore

    store = LocalRecordStore(root=str(tmp_path / "records"))
    return AnalysisWorkflow(record_store=store, executor=executor), store


async def test_run_pauses_for_review_with_report(tmp_path) -> None:
    """B1: run() 启动后进入审阅等待，interrupt payload 中含执行报告"""
    workflow, _ = await _make_workflow(tmp_path)
    execution = await workflow.run(
        session_id="s1", plan=_plan(), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    interrupt = await workflow.wait_for_review(execution)
    assert "report" in interrupt
    report = interrupt["report"]
    assert report["steps"][0]["method"] == "describe"


async def test_accept_delivers(tmp_path) -> None:
    """B2: 审阅 accept 后执行关闭，delivered=True，report 为本次 plan 结果"""
    workflow, _ = await _make_workflow(tmp_path)
    execution = await workflow.run(
        session_id="s2", plan=_plan(), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    await workflow.wait_for_review(execution)
    await workflow.review(execution, {"decision": "accept"})
    state = execution.result.get_state("delivered")
    assert state is True
    report = execution.result.get_state("report")
    assert report["steps"][0]["result"]["stats"]["sales"]["count"] == 4


async def test_revise_reexecutes_new_plan(tmp_path) -> None:
    """B3: revise 携带新 plan 重新执行并再次等待；accept 后最终 report 为新 plan 结果"""
    workflow, _ = await _make_workflow(tmp_path)
    execution = await workflow.run(
        session_id="s3", plan=_plan("sales"), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    await workflow.wait_for_review(execution)
    new_plan = AnalysisPlan(
        message="修正方案",
        steps=[
            PlanStep(
                title="相关性", method="correlation",
                target_columns=["sales"], chart_type="none",
            rationale="测试依据：数值列与任务匹配", )
        ],
    )
    await workflow.review(execution, {"decision": "revise", "plan": new_plan.model_dump()})
    interrupt = await workflow.wait_for_review(execution)
    assert interrupt["report"]["steps"][0]["method"] == "correlation"
    await workflow.review(execution, {"decision": "accept"})
    report = execution.result.get_state("report")
    assert report["steps"][0]["method"] == "correlation"


async def test_execution_record_persisted(tmp_path) -> None:
    """B4: 执行完成后 RecordStore 可按 session_id 查到执行记录"""
    workflow, store = await _make_workflow(tmp_path)
    execution = await workflow.run(
        session_id="s4", plan=_plan(), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    await workflow.wait_for_review(execution)
    await workflow.review(execution, {"decision": "accept"})
    refs = await workflow.list_execution_records("s4")
    assert len(refs) == 1
    content = await store.get(refs[0])
    assert '"describe"' in content


async def test_execute_runs_off_event_loop(tmp_path) -> None:
    """P1: 同步统计计算移入线程池——执行期间事件循环保持响应，on_step 可正常派发。"""
    executor = SlowExecutor(delay=0.05, steps=4)
    workflow, _ = await _make_workflow(tmp_path, executor=executor)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    heartbeat_task = asyncio.create_task(heartbeat())
    execution = await workflow.run(
        session_id="s-loop", plan=_plan(), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    interrupt = await workflow.wait_for_review(execution, timeout=5.0)
    heartbeat_task.cancel()
    assert "report" in interrupt
    # 约 0.2s 执行期 + 前后窗口：阻塞事件循环时 ticks 远低于 5
    assert ticks >= 5, f"事件循环疑似被阻塞：ticks={ticks}"
    # 执行体确实在工作线程（主线程保持可调度）
    assert executor.execute_thread is not None
    assert executor.execute_thread != threading.get_ident()


async def test_wait_for_review_timeout_starts_after_execution(tmp_path) -> None:
    """P1: 审阅超时只对「执行完成后」的等待计时，执行耗时不再计入。"""
    executor = SlowExecutor(delay=0.15, steps=3)  # 执行约 0.45s
    workflow, _ = await _make_workflow(tmp_path, executor=executor)
    execution = await workflow.run(
        session_id="s-timeout", plan=_plan(), df=_df(), artifact_dir=tmp_path / "artifacts"
    )
    # 审阅等待窗口 0.2s：若从 wait_for_review 调用起算（缺陷行为）必然超时
    interrupt = await workflow.wait_for_review(execution, timeout=0.2)
    assert "report" in interrupt

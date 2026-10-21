"""005 TriggerFlow 分析工作流：run/review 公共接口测试。"""
import pandas as pd

from medsta.agents.discussion import AnalysisPlan, PlanStep
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


async def _make_workflow(tmp_path):
    from agently.core.storage import LocalRecordStore

    store = LocalRecordStore(root=str(tmp_path / "records"))
    return AnalysisWorkflow(record_store=store), store


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

"""014 出图确认流：chart_config / chart_choice / 拼图 / 导出。"""
import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.app import create_app
from medsta.session.service import SessionService


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="方案",
        steps=[
            PlanStep(title="组间比较", method="group_compare", target_columns=["value"],
                     chart_type="boxplot", params={"group_column": "sex"}, rationale="两组比较"),
            PlanStep(title="描述统计", method="describe", target_columns=["value"],
                     chart_type="none", params={}, rationale="概览"),
        ],
        options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
    )


class _FakeGateway:
    async def request_structured_stream(self, schema, *, fields, input=None, info=None,
                                        instruct="", on_delta=None):
        return _plan()


def _collector():
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    return sent, _send


@pytest.fixture()
def service(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=DiscussionAgent(gateway=_FakeGateway()),
                             record_store=store, data_root=tmp_path)
    sid = service.create_session()
    service.attach_dataframe(
        sid, df=pd.DataFrame({"value": [3.0, 1.5, 4.2, 2.8, 5.1, 3.7],
                              "sex": ["F", "M", "F", "M", "F", "M"]}),
        dataset_path="mem.csv",
    )
    from medsta.session.manager import manager

    manager.get(sid).data.type_confirmed = True
    return service, sid


async def test_confirm_with_chart_steps_requests_config(service) -> None:
    """B1: 确认后存在带图步骤 → chart_config 请求而非直接执行"""
    service, sid = service
    sent, send = _collector()
    await service.handle(sid, {"type": "chat", "content": "比较两组"}, send)
    await service.wait_idle(sid)
    await service.handle(sid, {"type": "confirm_plan"}, send)
    config = [m for m in sent if m["type"] == "chart_config"]
    assert config and config[0]["steps"][0]["default_chart"] == "boxplot"
    assert service.get_status(sid) == "plan_confirmed"


async def test_chart_choice_applies_overrides_and_executes(service) -> None:
    """B2: chart_choice 覆盖图表类型与 α 后执行"""
    service, sid = service
    sent, send = _collector()
    await service.handle(sid, {"type": "chat", "content": "比较两组"}, send)
    await service.wait_idle(sid)
    await service.handle(sid, {"type": "confirm_plan"}, send)
    await service.handle(
        sid,
        {"type": "chart_choice", "choices": [{"step_id": "step_1", "chart_type": "violin"}],
         "alpha": 0.01, "correction": "holm"},
        send,
    )
    review = [m for m in sent if m["type"] == "review_request"]
    assert review
    step = review[0]["report"]["steps"][0]
    assert step["artifact"] and "violin" in step["artifact"]
    assert step["result"]["alpha"] == 0.01


async def test_shared_layout_renders_combined(tmp_path) -> None:
    """B3: shared 布局在多图时输出拼图"""
    from medsta.pipeline.executor import PipelineExecutor

    df = pd.DataFrame({"value": [3.0, 1.5, 4.2, 2.8, 5.1, 3.7],
                       "sex": ["F", "M", "F", "M", "F", "M"]})
    plan = AnalysisPlan(
        message="方案",
        steps=[
            PlanStep(title="组间比较", method="group_compare", target_columns=["value"],
                     chart_type="boxplot",
                     params={"group_column": "sex", "_layout": "shared"},
                     rationale="两组比较"),
            PlanStep(title="分布", method="describe", target_columns=["value"],
                     chart_type="histogram", params={"_layout": "shared"},
                     rationale="分布概览"),
        ],
        options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
    )
    artifacts_dir = tmp_path / "artifacts"
    report = PipelineExecutor().execute(df, plan, artifacts_dir)
    artifacts = [step.artifact for step in report.steps if step.artifact]
    assert artifacts.count("charts_combined.png") == 2
    assert (artifacts_dir / "charts_combined.png").exists()


async def test_export_csv_and_xlsx(service) -> None:
    """B5: /export 导出 csv 与 xlsx"""
    from fastapi.testclient import TestClient

    service, sid = service
    sent, send = _collector()
    await service.handle(sid, {"type": "chat", "content": "比较两组"}, send)
    await service.wait_idle(sid)
    await service.handle(sid, {"type": "confirm_plan"}, send)
    await service.handle(sid, {"type": "chart_choice", "use_default": True}, send)

    client = TestClient(create_app())
    client.app.state.service = service  # type: ignore[attr-defined]
    resp = client.get(f"/export/{sid}/0?format=csv")
    assert resp.status_code == 200 and "text/csv" in resp.headers["content-type"]
    resp = client.get(f"/export/{sid}/0?format=xlsx")
    assert resp.status_code == 200 and "spreadsheetml" in resp.headers["content-type"]
    resp = client.get(f"/export/{sid}/0?format=xml")
    assert resp.status_code == 400

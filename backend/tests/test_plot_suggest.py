"""017 交付追问：plot_suggest / plot_later 单步补渲染。"""
import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.service import SessionService


class _FakeGateway:
    async def request_structured_stream(self, schema, *, fields, input=None, info=None,
                                        instruct="", on_delta=None):
        return AnalysisPlan(
            message="方案",
            steps=[
                PlanStep(title="组间比较", method="group_compare", target_columns=["value"],
                         chart_type="none", params={"group_column": "sex"}, rationale="先看差异")
            ],
            options=[PlanOption(id="confirm", label="执行", action="confirm")],
        )


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
        sid, df=pd.DataFrame({"value": [1.0, 2.0, 3.5, 4.0, 5.5, 6.0],
                              "sex": ["F", "M"] * 3}), dataset_path="mem.csv"
    )
    service.set_column_type(sid, list(
        __import__("medsta.session.manager", fromlist=["manager"]).manager.get(sid).datasets.keys()
    )[0], "value", "continuous")
    return service, sid


async def test_table_delivery_triggers_plot_suggest(service) -> None:
    """B2/B4: 有 table 无图的步骤交付后发 plot_suggest"""
    service, sid = service
    sent, send = _collector()
    await service.handle(sid, {"type": "chat", "content": "比较两组"}, send)
    await service.wait_idle(sid)
    await service.handle(sid, {"type": "confirm_plan"}, send)
    review = [m for m in sent if m["type"] == "review_request"]
    assert review
    suggest = [m for m in sent if m["type"] == "plot_suggest"]
    assert suggest and suggest[0]["steps"][0]["charts"][0] in ("boxplot", "violin")


async def test_plot_later_renders_and_updates_report(service) -> None:
    """B3: plot_later 单步补渲染并重发更新后的 review_request"""
    service, sid = service
    sent, send = _collector()
    await service.handle(sid, {"type": "chat", "content": "比较两组"}, send)
    await service.wait_idle(sid)
    await service.handle(sid, {"type": "confirm_plan"}, send)
    before = [m for m in sent if m["type"] == "review_request"]
    assert before[0]["report"]["steps"][0]["artifact"] is None

    await service.handle(
        sid, {"type": "plot_later", "step_index": 0, "chart_type": "violin"}, send
    )
    updated = [m for m in sent if m["type"] == "review_request" and m.get("updated")]
    assert updated
    step = updated[-1]["report"]["steps"][0]
    assert step["artifact"] and "violin" in step["artifact"]

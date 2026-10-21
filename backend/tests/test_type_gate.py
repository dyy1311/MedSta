"""016 前置类型确认：未敲定时拦截 chat，确认后自动继续。"""
import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.service import SessionService


class _FakeGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def request_structured_stream(self, schema, *, fields, input=None, info=None,
                                        instruct="", on_delta=None):
        self.calls += 1
        if "sex" in (info or ""):
            pass
        return AnalysisPlan(
            message="方案",
            steps=[
                PlanStep(title="描述", method="describe", target_columns=["age"],
                         chart_type="none", params={}, rationale="连续列概览")
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
        sid, df=pd.DataFrame({"age": [25.0, 31.0, 42.0], "sex": ["F", "M", "F"]}),
        dataset_path="d.csv",
    )
    return service, sid


async def test_chat_blocked_until_types_confirmed(service) -> None:
    """B6: 未敲定类型 → type_review 事件且不调模型；确认后自动继续生成方案"""
    service, sid = service
    gateway = service._agent._gateway
    sent, send = _collector()

    await service.handle(sid, {"type": "chat", "content": "分析年龄"}, send)
    reviews = [m for m in sent if m["type"] == "type_review"]
    assert reviews and gateway.calls == 0
    assert any(col["name"] == "age" for col in reviews[0]["columns"])

    await service.handle(
        sid,
        {"type": "type_confirm", "types": {"age": "continuous", "sex": "categorical"}},
        send,
    )
    confirmed = [m for m in sent if m["type"] == "type_confirmed"]
    assert confirmed
    await service.wait_idle(sid)
    assert gateway.calls == 1
    plans = [m for m in sent if m["type"] == "plan"]
    assert plans  # pending chat 自动继续


async def test_workspace_switch_carries_type_confirmed(service) -> None:
    """切换工作区推送 type_confirmed 状态"""
    service, sid = service
    sent, send = _collector()
    await service.handle(
        sid, {"type": "type_confirm", "types": {"age": "continuous"}}, send
    )
    service.attach_dataframe(
        sid, df=pd.DataFrame({"x": [1.0, 2.0]}), dataset_path="second.csv"
    )
    ds2 = list(__import__("medsta.session.manager", fromlist=["manager"]).manager
               .get(sid).datasets.keys())[-1]
    await service.handle(sid, {"type": "workspace", "dataset_id": ds2}, send)
    profiles = [m for m in sent if m["type"] == "data_profile"]
    assert profiles[-1]["type_confirmed"] is False

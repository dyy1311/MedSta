"""011 能力披露与选项路由测试。"""
import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore
from fastapi.testclient import TestClient

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.app import create_app
from medsta.session.service import SessionService


def test_capabilities_endpoint_lists_methods_and_charts() -> None:
    """B1: GET /capabilities 返回方法目录、图表类型与规划中能力"""
    client = TestClient(create_app())
    body = client.get("/capabilities").json()
    names = {tool["name"] for tool in body["tools"]}
    assert {"describe", "group_compare", "regression", "missing_report"} <= names
    chart_names = {item["name"] for item in body["charts"]}
    assert {"histogram", "qq_plot", "violin", "residual_plot"} <= chart_names
    planned = {item["name"] for item in body["planned"]}
    assert "survival_analysis" in planned


class _FakeGateway:
    def __init__(self, plan: AnalysisPlan) -> None:
        self._plan = plan

    async def request_structured_stream(self, schema, *, fields, input=None, info=None,
                                        instruct="", on_delta=None):
        self.last_input = input
        if on_delta is not None:
            await on_delta("…")
        return self._plan


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="方案",
        steps=[
            PlanStep(title="描述统计", method="describe", target_columns=["age"],
                     chart_type="none", params={}, rationale="测试依据：数值列与任务匹配")
        ],
        options=[
            PlanOption(id="confirm", label="按此执行", action="confirm"),
            PlanOption(id="revise", label="换方法", action="revise"),
            PlanOption(id="explain", label="解释依据", action="explain"),
        ],
    )


def _collector():
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    return sent, _send


@pytest.fixture()
def env(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    session_id = service.create_session()
    service.attach_dataframe(
        session_id,
        df=pd.DataFrame({"age": [25.0, 31.0, 42.0], "sex": ["F", "M", "F"]}),
        dataset_path="mem.csv",
    )
    from medsta.session.manager import manager

    manager.get(session_id).data.type_confirmed = True
    service.set_agent(DiscussionAgent(gateway=_FakeGateway(_plan())))
    return service, session_id


async def test_option_confirm_runs_plan(env) -> None:
    """B2: option=confirm 等价确认执行"""
    service, session_id = env
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析"}, send)
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "option", "option_id": "confirm"}, send)
    assert any(m["type"] == "review_request" for m in sent)


async def test_option_supplement_returns_to_discussion(env) -> None:
    """B3: option=custom/supplement 携带文本回到讨论并生成新方案"""
    service, session_id = env
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析"}, send)
    await service.wait_idle(session_id)
    await service.handle(
        session_id,
        {"type": "option", "option_id": "explain", "content": "为什么用描述统计"},
        send,
    )
    await service.wait_idle(session_id)
    assert sum(1 for m in sent if m["type"] == "plan") >= 2


async def test_unknown_option_rejected(env) -> None:
    """B4: 未知 option_id 返回 INVALID_PARAM"""
    service, session_id = env
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析"}, send)
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "option", "option_id": "nope"}, send)
    errors = [m for m in sent if m["type"] == "error"]
    assert errors and errors[-1]["code"] == "INVALID_PARAM"

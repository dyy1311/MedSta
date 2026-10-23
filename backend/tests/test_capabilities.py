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
    assert "survival_analysis" in names
    assert "survival_analysis" not in planned
    assert "competing_risk" in planned
    assert "sap_export" in planned


def test_capabilities_lists_textbook_tools() -> None:
    """023 B18: 教材口径的统计描述与参考值范围进入能力披露。"""
    client = TestClient(create_app())
    body = client.get("/capabilities").json()
    tools = {tool["name"]: tool for tool in body["tools"]}

    assert "descriptive_stats" in tools
    assert "reference_range" in tools
    assert {"one_sample_test", "randomized_block_anova", "mcnemar_test"} <= set(tools)
    assert {
        "factorial_anova", "repeated_measures_anova", "sample_size"
    } <= set(tools)
    assert tools["sample_size"]["charts"] == []
    assert {param["name"] for param in tools["sample_size"]["params"]} >= {
        "design", "solve", "effect_size", "alpha", "power"
    }
    assert {param["name"] for param in tools["reference_range"]["params"]} == {
        "percentage", "sides", "method"
    }
    assert tools["reference_range"]["charts"] == []
    assert "histogram" in tools["descriptive_stats"]["charts"]


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


def test_planned_entries_declare_unimplemented_scope() -> None:
    """030 B2: 每条规划中能力必须写明未实现/不支持的范围。

    只列方法名而不表态，会让读者误以为整块能力都还没有；一旦方法落地，
    模糊清单也不会主动提醒作者回头修改。
    """
    from medsta.api.routes_capabilities import _PLANNED

    offenders = [
        item["name"]
        for item in _PLANNED
        if "未实现" not in item["description"] and "不支持" not in item["description"]
    ]

    assert offenders == []


def test_planned_names_do_not_collide_with_registry() -> None:
    """030 B3: 规划中能力不得与已注册工具重名（防止已实现仍挂 planned）。"""
    from medsta.api.routes_capabilities import _PLANNED
    from medsta.stats import registry

    registered = {spec.name for spec in registry.all_tools()} | set(registry.ALIASES)
    planned = {item["name"] for item in _PLANNED}

    assert planned & registered == set()


def test_multiplicity_description_separates_implemented_and_missing() -> None:
    """030 B1: 多重性条目必须同时写清已实现与未实现部分。"""
    from medsta.api.routes_capabilities import _PLANNED

    item = next(entry for entry in _PLANNED if entry["name"] == "multiplicity_control")
    description = item["description"]

    assert "已实现" in description
    assert "Holm" in description and "Dunnett" in description
    assert "Hochberg" in description or "gatekeeping" in description

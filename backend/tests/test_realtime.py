"""010 实时交互：错误分类、流式输出、中断/继续、步骤进度。"""
import asyncio

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.service import SessionService


class FakeGateway:
    """流式网关替身：先吐两段 delta，再返回结构化计划。"""

    def __init__(self, plan: AnalysisPlan | None = None, fail: bool = False) -> None:
        self._plan = plan or _plan()
        self._fail = fail
        self.deltas = ["正在分析", "数据画像…"]

    async def request_structured_stream(
        self, schema, *, fields, input=None, info=None, instruct="", on_delta=None
    ):
        if self._fail:
            from medsta.errors import AppError, ErrorCode

            raise AppError(
                ErrorCode.MODEL_REQUEST_FAILED,
                "模型请求失败：连接超时",
                hint="检查网络或 LLM_BASE_URL 配置",
            )
        for piece in self.deltas:
            if on_delta is not None:
                await on_delta(piece)
            await asyncio.sleep(0)
        return self._plan


def _plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="建议先做描述统计",
        steps=[
            PlanStep(
                title="描述统计", method="describe", target_columns=["age"],
                chart_type="histogram", params={},
            rationale="测试依据：数值列与任务匹配", )
        ],
        options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
    )


def _collector():
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    return sent, _send


@pytest.fixture()
def service_env(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    session_id = service.create_session()
    df = pd.DataFrame({"age": [25.0, 31.0, 42.0, 38.0], "sex": ["F", "M", "F", "M"]})
    service.attach_dataframe(session_id, df=df, dataset_path="mem.csv")
    from medsta.session.manager import manager

    manager.get(session_id).data.type_confirmed = True
    return service, session_id, store


async def test_chat_streams_deltas_then_plan(service_env) -> None:
    """B1: 讨论流式输出 delta，随后下发含选项的 plan 事件"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, send)
    await service.wait_idle(session_id)

    deltas = [m for m in sent if m["type"] == "stream"]
    assert "".join(m["delta"] for m in deltas).startswith("正在分析")
    plan_events = [m for m in sent if m["type"] == "plan"]
    assert plan_events and plan_events[0]["options"][0]["action"] == "confirm"


async def test_model_failure_is_visible(service_env) -> None:
    """B2: 模型请求失败 → error 事件含错误码与修复建议"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway(fail=True)))
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, send)
    await service.wait_idle(session_id)

    errors = [m for m in sent if m["type"] == "error"]
    assert errors and errors[-1]["code"] == "MODEL_REQUEST_FAILED"
    assert errors[-1]["hint"]


async def test_interrupt_during_generation(service_env) -> None:
    """B3: 生成中可中断，收到 interrupted 事件并回到 discussing"""
    service, session_id, _ = service_env

    class SlowGateway(FakeGateway):
        async def request_structured_stream(self, *args, **kwargs):
            await asyncio.sleep(5)
            return _plan()

    service.set_agent(DiscussionAgent(gateway=SlowGateway()))
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, send)
    await asyncio.sleep(0.05)
    await service.handle(session_id, {"type": "interrupt"}, send)
    await asyncio.sleep(0.05)

    kinds = [m["type"] for m in sent]
    assert "interrupted" in kinds
    assert service.get_status(session_id) == "discussing"


async def test_confirm_emits_step_progress(service_env) -> None:
    """B4: 执行时下发步骤进度与 review_request"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, send)
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, send)
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, send)

    progress = [
        m for m in sent if m["type"] == "progress" and m.get("stage") == "executing"
    ]
    assert progress and progress[0]["total"] == 1
    assert progress[0]["step"] == 1
    assert any(m["type"] == "review_request" for m in sent)


async def test_resume_after_interrupt(service_env) -> None:
    """B5: 中断后 resume 回到讨论态并提示可继续"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await service.handle(session_id, {"type": "resume"}, send)
    kinds = [m["type"] for m in sent]
    assert "resumed" in kinds

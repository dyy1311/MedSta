"""010 实时交互：错误分类、流式输出、中断/继续、步骤进度。"""
import asyncio

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.manager import InvalidStateTransition, SessionStatus, manager
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


# ---- P1 编排守卫：忙锁 / 超时清理 / 状态机转移表 ----


def _table_plan() -> AnalysisPlan:
    """无图表步骤的方案：confirm 直接进入执行（不经过 chart_config）。"""
    return AnalysisPlan(
        message="只出统计表",
        steps=[
            PlanStep(
                title="描述统计", method="describe", target_columns=["age"],
                chart_type="none", params={},
                rationale="测试依据：数值列与任务匹配",
            )
        ],
        options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
    )


class GatedGateway(FakeGateway):
    """可门控的假网关：等待外部放行后才返回方案。"""

    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__()
        self._gate = gate

    async def request_structured_stream(self, *args, **kwargs):
        await self._gate.wait()
        return await super().request_structured_stream(*args, **kwargs)


class TimeoutWorkflow:
    """假工作流：wait_for_review 恒超时，用于验证超时后的残留清理。"""

    def __init__(self) -> None:
        self.cancelled = False

    async def run(self, **kwargs):
        return object()

    async def wait_for_review(self, execution, timeout=10.0):
        raise TimeoutError("等待审阅超时：执行未进入 plan_review 等待")

    async def review(self, execution, decision):
        return None

    async def cancel(self, execution, reason="cancelled"):
        self.cancelled = True


async def test_second_chat_rejected_while_busy(service_env) -> None:
    """P1: 同会话生成进行中再发 chat → SESSION_BUSY 错误帧，不并发第二任务。"""
    service, session_id, _ = service_env
    gate = asyncio.Event()
    service.set_agent(DiscussionAgent(gateway=GatedGateway(gate)))
    first, send1 = _collector()
    await service.handle(session_id, {"type": "chat", "content": "第一问"}, send1)
    await asyncio.sleep(0.01)
    second, send2 = _collector()
    await service.handle(session_id, {"type": "chat", "content": "第二问"}, send2)

    busy = [m for m in second if m.get("type") == "error"]
    assert len(busy) == 1 and busy[0]["code"] == "SESSION_BUSY"

    gate.set()
    await service.wait_idle(session_id)
    assert any(m.get("type") == "plan" for m in first)


async def test_review_timeout_cleans_up_stale_execution(service_env) -> None:
    """P1: 审阅等待超时后取消工作流并清理残留执行，后续 review 不得交付旧执行。"""
    service, session_id, _ = service_env
    workflow = TimeoutWorkflow()
    service._workflow_factory = lambda: workflow
    manager.get(session_id).plan = _table_plan()
    sent, send = _collector()

    await service.handle(session_id, {"type": "confirm_plan"}, send)

    assert any(m.get("type") == "error" for m in sent)
    assert workflow.cancelled is True
    assert service._executions.get(session_id) is None
    assert service._workflows.get(session_id) is None
    assert service.get_status(session_id) == "discussing"

    # 残留已清理：review 无法再把「已报错的执行」交付掉
    after, send2 = _collector()
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send2)
    assert any(m.get("code") == "NO_ACTIVE_RUN" for m in after)


async def test_confirm_plan_rejected_after_delivery(service_env) -> None:
    """P1: 交付态重复 confirm_plan 被状态守卫拒绝，不再用残留旧方案重执行。"""
    service, session_id, _ = service_env
    session = manager.get(session_id)
    session.plan = _table_plan()
    session.status = SessionStatus.DELIVERED
    sent, send = _collector()

    await service.handle(session_id, {"type": "confirm_plan"}, send)

    kinds = [m.get("type") for m in sent]
    assert "review_request" not in kinds
    assert "delivered" not in kinds
    assert "error" in kinds


def test_transition_rejects_invalid_jump() -> None:
    """P1: 状态机转移表守卫：非法跳跃抛 InvalidStateTransition，合法链路不受影响。"""
    session = manager.create_session()
    sid = session.session_id

    with pytest.raises(InvalidStateTransition):
        manager.transition(sid, SessionStatus.DELIVERED)  # discussing ⇏ delivered

    manager.transition(sid, SessionStatus.PLAN_CONFIRMED)
    manager.transition(sid, SessionStatus.EXECUTING)
    manager.transition(sid, SessionStatus.DELIVERED)
    manager.transition(sid, SessionStatus.DISCUSSING)  # 修正回讨论

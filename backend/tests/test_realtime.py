"""010 实时交互：错误分类、流式输出、中断/继续、步骤进度。"""
import asyncio

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.pipeline.executor import PipelineExecutor
from medsta.pipeline.workflow import AnalysisWorkflow
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
    # 中断帧只发一次：此前 _on_interrupt 与被取消任务各发一帧
    assert kinds.count("interrupted") == 1
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
    # 执行经后台任务驱动（批次 8），等待审阅请求送达后再取进度帧
    await service.wait_idle(session_id)

    progress = [
        m for m in sent if m["type"] == "progress" and m.get("stage") == "executing"
    ]
    assert progress and progress[0]["total"] == 1
    assert progress[0]["step"] == 1
    assert any(m["type"] == "review_request" for m in sent)


async def test_resume_after_interrupt(service_env) -> None:
    """B5: 中断后 resume 回到讨论态。"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await service.handle(session_id, {"type": "resume"}, send)
    resumed_frames = [m for m in sent if m["type"] == "resumed"]
    assert resumed_frames
    # 批次11：讨论态 resume 不再附带「已回到讨论态」提示文案——
    # 该文案与事件流回放里的历史提示帧重复渲染（恢复会话时出现两条相同气泡）
    assert resumed_frames[0].get("message") in (None, "")


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

    def create(self, **kwargs):
        return object()

    async def start(self, execution):
        return None

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
    # 超时错误经后台任务异步下发（批次 8），等待任务收尾
    await service.wait_idle(session_id)

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


# ---- 审查修复批（P0）：busy 泄漏 / 执行期 chat 门控 / resume 降级 ----


class FlakyInterpretAgent:
    """答疑替身：answer 恒失败（模拟模型故障），统计调用次数。"""

    def __init__(self) -> None:
        self.calls = 0

    def interpret(self, **kwargs):
        return None

    def answer(self, **kwargs):
        self.calls += 1
        raise RuntimeError("模拟答疑模型故障")


class SlowExecutor(PipelineExecutor):
    """慢执行器：计算前 sleep，用于暴露「执行中收到 resume」的时序窗口。"""

    def execute(self, df, plan, artifact_dir, on_step=None):
        import time

        time.sleep(0.2)
        return super().execute(df, plan, artifact_dir, on_step=on_step)


async def _reach_review_request(service, session_id, send) -> None:
    """公共前置：讨论 → confirm → chart_choice → 审阅等待（状态 executing）。"""
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, send)
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, send)
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, send)
    # 执行经后台任务驱动（批次 8），等待审阅请求送达
    await service.wait_idle(session_id)


async def test_answer_failure_does_not_wedge_session(service_env) -> None:
    """P0: 答疑失败（reply=None 提前 return）不得泄漏忙锁——后续 chat 不得 SESSION_BUSY。"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    flaky = FlakyInterpretAgent()
    service.set_interpret_agent(flaky)
    sent, send = _collector()
    await _reach_review_request(service, session_id, send)
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send)
    assert service.get_status(session_id) == "delivered"

    first, send1 = _collector()
    await service.handle(session_id, {"type": "chat", "content": "这个结果说明什么"}, send1)
    await service.wait_idle(session_id)
    assert any(m.get("code") == "MODEL_REQUEST_FAILED" for m in first)
    assert flaky.calls == 1

    second, send2 = _collector()
    await service.handle(session_id, {"type": "chat", "content": "p 值怎么看"}, send2)
    await service.wait_idle(session_id)
    codes = [m.get("code") for m in second if m.get("type") == "error"]
    assert "SESSION_BUSY" not in codes
    assert flaky.calls == 2


async def test_chat_rejected_while_awaiting_review(service_env) -> None:
    """P0: 审阅等待（executing）中 chat 必须被拒——不得降级状态机或覆盖执行中的方案。"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await _reach_review_request(service, session_id, send)
    assert service.get_status(session_id) == "executing"

    second, send2 = _collector()
    await service.handle(session_id, {"type": "chat", "content": "再帮我看年龄分布"}, send2)
    await service.wait_idle(session_id)

    assert not any(m.get("type") == "plan" for m in second)
    codes = [m.get("code") for m in second if m.get("type") == "error"]
    assert codes == ["SESSION_BUSY"]
    assert service.get_status(session_id) == "executing"

    # 审阅链路未被破坏：accept 仍可正常交付
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send2)
    assert service.get_status(session_id) == "delivered"


async def test_resume_during_execution_keeps_state(service_env) -> None:
    """P0: 执行中收到 resume 不降级状态机；执行完成后审阅/交付链路保持可用。"""
    service, session_id, store = service_env
    service._workflow_factory = lambda: AnalysisWorkflow(
        executor=SlowExecutor(), record_store=store
    )
    manager.get(session_id).plan = _table_plan()
    sent, send = _collector()

    confirm_task = asyncio.create_task(
        service.handle(session_id, {"type": "confirm_plan"}, send)
    )
    # 计算窗口 = 状态翻转为 executing 起、到 _executions 登记前
    # （async_start 会阻塞到流程暂停；此窗口内 resume 模拟第二连接/刷新）
    for _ in range(200):
        if service.get_status(session_id) == "executing":
            break
        await asyncio.sleep(0.01)
    assert service.get_status(session_id) == "executing", "执行未启动"
    resumed, resume_send = _collector()
    await service.handle(session_id, {"type": "resume"}, resume_send)

    frames = [m for m in resumed if m.get("type") == "resumed"]
    assert frames and frames[0]["stage"] == "executing"
    assert service.get_status(session_id) == "executing"

    await confirm_task
    # 执行经后台任务驱动（批次 8），等待审阅请求送达
    await service.wait_idle(session_id)
    assert any(m.get("type") == "review_request" for m in sent)
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send)
    assert service.get_status(session_id) == "delivered"


# ---- 审查修复批（P1 状态守卫族）：异常 teardown / 句柄清理 / 单一中断帧 ----


class ExplodingWorkflow:
    """假工作流：create 阶段抛非预期异常，验证执行编排异常路径的残留清理。"""

    def __init__(self) -> None:
        self.cancelled = False

    def create(self, **kwargs):
        raise RuntimeError("执行编排异常")

    async def start(self, execution):
        raise AssertionError("不应启动执行")

    async def review(self, execution, decision):
        return None

    async def cancel(self, execution, reason="cancelled"):
        self.cancelled = True


async def test_execute_plan_exception_tears_down_workflow(service_env) -> None:
    """P1: 执行编排异常必须 teardown——不残留句柄，也不留可交付的旧执行。"""
    service, session_id, _ = service_env
    workflow = ExplodingWorkflow()
    service._workflow_factory = lambda: workflow
    manager.get(session_id).plan = _table_plan()
    sent, send = _collector()

    await service.handle(session_id, {"type": "confirm_plan"}, send)

    assert any(m.get("type") == "error" for m in sent)
    assert service._workflows.get(session_id) is None
    assert service._executions.get(session_id) is None
    assert service.get_status(session_id) == "discussing"

    after, send2 = _collector()
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send2)
    assert any(m.get("code") == "NO_ACTIVE_RUN" for m in after)


async def test_review_decisions_clear_workflow_handles(service_env) -> None:
    """P1: revise 与 accept 都要清理 _workflows/_executions，防句柄泄漏与残留可交付。"""
    service, session_id, _ = service_env
    service.set_agent(DiscussionAgent(gateway=FakeGateway()))
    sent, send = _collector()
    await _reach_review_request(service, session_id, send)
    assert service._workflows.get(session_id) is not None

    await service.handle(
        session_id, {"type": "review", "decision": "revise", "content": "换个方法"}, send
    )
    assert service._workflows.get(session_id) is None
    assert service._executions.get(session_id) is None
    assert service.get_status(session_id) == "discussing"

    # 再次执行 → accept 同样清理
    await _reach_review_request(service, session_id, send)
    await service.handle(session_id, {"type": "review", "decision": "accept"}, send)
    assert service.get_status(session_id) == "delivered"
    assert service._workflows.get(session_id) is None
    assert service._executions.get(session_id) is None


async def test_interrupt_during_compute_is_immediate(service_env) -> None:
    """P1(批次8): 执行期 WS 收包不阻塞——计算进行中 interrupt 立即生效。

    此前 `_execute_plan` 占用 WS handler 直至审阅暂停：计算期间 interrupt
    排队，待审阅请求发出后才被处理（中断名存实亡，且已送出审阅请求）。
    """
    service, session_id, store = service_env
    service._workflow_factory = lambda: AnalysisWorkflow(
        executor=SlowExecutor(), record_store=store
    )
    manager.get(session_id).plan = _table_plan()
    sent, send = _collector()

    await service.handle(session_id, {"type": "confirm_plan"}, send)

    # 句柄同步登记（create 与启动分离）；计算 sleep 0.2s 进行中
    for _ in range(200):
        if service._executions.get(session_id) is not None:
            break
        await asyncio.sleep(0.01)
    assert service._executions.get(session_id) is not None, "执行未启动"
    assert service.get_status(session_id) == "executing"

    await service.handle(session_id, {"type": "interrupt"}, send)

    assert any(m.get("type") == "interrupted" for m in sent)
    # 中断发生在计算完成之前：不得先送出审阅请求
    assert not any(m.get("type") == "review_request" for m in sent)
    assert service.get_status(session_id) == "discussing"

    await service.wait_idle(session_id)  # 被取消任务的后台收尾
    assert service._workflows.get(session_id) is None
    assert service._executions.get(session_id) is None


async def test_release_task_slot_ignores_stale_task(tmp_path) -> None:
    """终审修复: 被取消的旧任务不得清掉新任务的登记与忙锁（跨任务误清理竞态）。

    interrupt 的取消是异步投递的：旧任务的 finally 可能晚于新任务登记执行。
    若无条件 pop/discard，后续 interrupt 找不到任务、忙锁丢失还会允许同会话双跑。
    """
    service = SessionService(record_store=LocalRecordStore(root=str(tmp_path / "records")))
    sid = service.create_session()
    newer = asyncio.create_task(asyncio.sleep(0.05))
    try:
        service._tasks[sid] = newer
        service._busy.add(sid)

        # 当前协程不是占位任务：等价于「旧任务在 finally 里收尾」
        service._release_task_slot(sid)

        assert service._tasks.get(sid) is newer
        assert sid in service._busy
    finally:
        newer.cancel()
        await asyncio.gather(newer, return_exceptions=True)
        service._tasks.pop(sid, None)
        service._busy.discard(sid)

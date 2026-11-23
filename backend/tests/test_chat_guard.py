"""043 输入守卫：模型只服务统计任务，拦截闲聊省 token。"""
from __future__ import annotations

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import DiscussionAgent
from medsta.session.manager import manager
from medsta.session.service import SessionService
from tests.helpers import PLAN_TABLE_ONLY, fake_agent


@pytest.fixture()
def service_env(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    session_id = service.create_session()
    df = pd.DataFrame({"group": ["A", "B"], "value": [1.0, 2.0]})
    service.attach_dataframe(session_id, df=df, dataset_path="mem.csv")
    manager.get(session_id).data.type_confirmed = True
    return service, session_id


async def _sent(service, session_id, event):
    frames: list[dict] = []

    async def send(message: dict) -> None:
        frames.append(message)

    await service.handle(session_id, event, send)
    await service.wait_idle(session_id)  # chat 走后台生成任务，等待完成再断言
    return frames


async def test_chitchat_rejected_before_model(service_env) -> None:
    """B1: 纯问候在宿主预筛层拒绝——不调模型（零 token）。"""
    service, session_id = service_env
    service.set_agent(DiscussionAgent(gateway=object()))  # 若被调用会异常暴露

    frames = await _sent(service, session_id, {"type": "chat", "content": "你好"})

    rejected = next(f for f in frames if f["type"] == "chat_rejected")
    assert "问候" in rejected["reason"]
    assert not any(f["type"] == "plan" for f in frames)


@pytest.mark.parametrize(
    "text", ["谢谢", "再见！", "ok", "嗯", "a", "   "]
)
async def test_chitchat_variants_rejected(service_env, text: str) -> None:
    """B1 变体：常见闲聊/无意义输入一律预筛拒绝。"""
    service, session_id = service_env
    service.set_agent(DiscussionAgent(gateway=object()))

    frames = await _sent(service, session_id, {"type": "chat", "content": text})

    assert any(f["type"] == "chat_rejected" for f in frames)


async def test_model_off_topic_rejected(service_env) -> None:
    """B2: 模型自检判定无关（off_topic=true）→ chat_rejected，不产方案。"""
    service, session_id = service_env
    plan_payload = {
        **PLAN_TABLE_ONLY,
        "off_topic": True,
        "off_topic_reason": "该请求是写诗，与统计分析无关",
    }
    service.set_agent(fake_agent(plan_payload))

    frames = await _sent(service, session_id, {"type": "chat", "content": "帮我写一首诗"})

    rejected = next(f for f in frames if f["type"] == "chat_rejected")
    assert "写诗" in rejected["reason"]
    assert not any(f["type"] == "plan" for f in frames)
    assert service.get_status(session_id) == "discussing"  # 状态不被破坏


async def test_on_topic_still_works(service_env) -> None:
    """B3 回归：正常统计请求不受守卫影响（off_topic=false 走原流程）。"""
    service, session_id = service_env
    service.set_agent(fake_agent(PLAN_TABLE_ONLY))

    frames = await _sent(service, session_id, {"type": "chat", "content": "分析 value 的分布"})

    assert any(f["type"] == "plan" for f in frames)
    assert not any(f["type"] == "chat_rejected" for f in frames)

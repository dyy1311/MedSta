"""006 会话编排 API：REST 上传 + SessionService 编排测试。"""
import io

import pandas as pd

from fastapi.testclient import TestClient

from medsta.app import create_app


CSV_CONTENT = (
    "age,city\n"
    "25,Beijing\n"
    "31,Shanghai\n"
    "42,Beijing\n"
).encode("utf-8")


def _client_with_session() -> tuple:
    client = TestClient(create_app())
    session_id = client.post("/sessions").json()["session_id"]
    return client, session_id


def test_upload_data_returns_profile() -> None:
    """B1: 上传 CSV 后返回 200 与画像摘要"""
    client, session_id = _client_with_session()
    resp = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("data.csv", io.BytesIO(CSV_CONTENT), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "data_profile"
    assert body["profile"]["row_count"] == 3
    assert body["profile"]["column_count"] == 2


# ---- SessionService 编排测试（模拟模型） ----

import pytest

from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import DiscussionAgent
from medsta.data.parser import load_table
from medsta.data.profiler import profile_dataframe
from medsta.pipeline.workflow import AnalysisWorkflow
from medsta.session.service import SessionService


class RecordingFakeRequest:
    """模拟模型：返回预置 plan，记录四段式以断言契约。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.instruct_value: str | None = None

    def input(self, value):
        return self

    def info(self, value):
        return self

    def instruct(self, value):
        self.instruct_value = value
        return self

    def output(self, fields, **kwargs):
        return self

    def start(self) -> dict:
        return self.payload


def _plan_payload(message: str = "建议方案") -> dict:
    return {
        "message": message,
        "steps": [
            {
                "title": "描述统计",
                "method": "describe",
                "target_columns": ["age"], "rationale": "测试依据",
                "chart_type": "histogram",
                "params": {},
            }
        ],
    }


@pytest.fixture()
def service_env(tmp_path):
    fake = RecordingFakeRequest(_plan_payload())
    agent = DiscussionAgent(request_factory=lambda: fake)
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=agent, record_store=store, data_root=tmp_path)
    return service, store, fake


def collect(sent: list) -> "object":
    async def _send(message: dict) -> None:
        sent.append(message)
    return _send


def _prepare_session(service: SessionService) -> str:
    session_id = service.create_session()
    df = pd.DataFrame({"age": [25.0, 31.0, 42.0], "city": ["a", "b", "a"]})
    service.attach_dataframe(session_id, df=df, dataset_path="mem.csv")
    from medsta.session.manager import manager

    manager.get(session_id).data.type_confirmed = True
    return session_id


async def test_chat_yields_plan(service_env) -> None:
    """B2: discussing 态发 chat 得到 plan 事件"""
    service, _, _ = service_env
    session_id = _prepare_session(service)
    sent: list[dict] = []
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, collect(sent))
    await service.wait_idle(session_id)
    plan_events = [m for m in sent if m["type"] == "plan"]
    assert len(plan_events) == 1
    assert plan_events[0]["steps"][0]["method"] == "describe"


async def test_confirm_starts_execution(service_env) -> None:
    """B3: confirm_plan 后收到 review_request（含 report）"""
    service, _, _ = service_env
    session_id = _prepare_session(service)
    sent: list[dict] = []
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, collect(sent))
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, collect(sent))
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, collect(sent))
    review_requests = [m for m in sent if m["type"] == "review_request"]
    assert len(review_requests) == 1
    assert review_requests[0]["report"]["steps"][0]["method"] == "describe"


async def test_accept_delivers(service_env) -> None:
    """B4: review accept 后收到 delivered，会话状态为 delivered"""
    service, _, _ = service_env
    session_id = _prepare_session(service)
    sent: list[dict] = []
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, collect(sent))
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, collect(sent))
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, collect(sent))
    await service.handle(session_id, {"type": "review", "decision": "accept"}, collect(sent))
    delivered = [m for m in sent if m["type"] == "delivered"]
    assert len(delivered) == 1
    assert service.get_status(session_id) == "delivered"


async def test_revise_returns_to_discussion(service_env) -> None:
    """B5: revise（带修正意见）后回到 discussing，再次 chat 的 instruct 含修正意见"""
    service, _, fake = service_env
    session_id = _prepare_session(service)
    sent: list[dict] = []
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, collect(sent))
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, collect(sent))
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, collect(sent))
    await service.handle(
        session_id,
        {"type": "review", "decision": "revise", "content": "不要用直方图"},
        collect(sent),
    )
    assert service.get_status(session_id) == "discussing"
    await service.handle(session_id, {"type": "chat", "content": "换个分析"}, collect(sent))
    await service.wait_idle(session_id)
    assert fake.instruct_value is not None
    assert "不要用直方图" in fake.instruct_value


async def test_session_records_persisted(service_env) -> None:
    """B6: chat 与交付事件写入 RecordStore，可按 session_id 查询"""
    service, store, _ = service_env
    session_id = _prepare_session(service)
    sent: list[dict] = []
    await service.handle(session_id, {"type": "chat", "content": "分析年龄"}, collect(sent))
    await service.wait_idle(session_id)
    await service.handle(session_id, {"type": "confirm_plan"}, collect(sent))
    await service.handle(session_id, {"type": "chart_choice", "use_default": True}, collect(sent))
    await service.handle(session_id, {"type": "review", "decision": "accept"}, collect(sent))
    refs = await store.search(filters={"collection": "sessions", "scope.session_id": session_id})
    assert len(refs) >= 2
    kinds = {ref["kind"] if isinstance(ref, dict) else ref.kind for ref in refs}
    assert "user_message" in kinds
    assert "delivery" in kinds

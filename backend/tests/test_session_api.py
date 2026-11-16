"""006 会话编排 API：REST 上传 + SessionService 编排测试。"""
import io
import pathlib

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore
from fastapi.testclient import TestClient

from medsta.agents.discussion import DiscussionAgent
from medsta.app import create_app
from medsta.session.service import SessionService

CSV_CONTENT = (
    b"age,city\n"
    b"25,Beijing\n"
    b"31,Shanghai\n"
    b"42,Beijing\n"
)


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


def test_upload_rejects_oversized_file(monkeypatch) -> None:
    """P1: 超过大小上限的上传被拒绝（413），不进入解析。"""
    client, session_id = _client_with_session()
    monkeypatch.setattr("medsta.api.routes_data.MAX_UPLOAD_BYTES", 64)
    oversized = b"group,value\n" + b"A,1.0\n" * 20  # > 64 bytes

    resp = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("big.csv", io.BytesIO(oversized), "text/csv")},
    )

    assert resp.status_code == 413
    assert "上限" in resp.json()["detail"]


# ---- 批量列类型修改（用户批量操作需求） ----


def _upload_two_numeric(client, session_id: str) -> str:
    resp = client.post(
        f"/sessions/{session_id}/data",
        files={
            "file": (
                "d.csv",
                io.BytesIO(b"group,value,age,score\nA,1,25,3.1\nB,2,31,4.2\n"),
                "text/csv",
            )
        },
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


def test_batch_column_types_updates_all_at_once() -> None:
    """批量：一次请求把多列改为指定类型，type_confirmed 置位，快照同步。"""
    import json

    client, session_id = _client_with_session()
    root = pathlib.Path(client.app.state.data_root)
    dataset_id = _upload_two_numeric(client, session_id)

    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"types": {"value": "continuous", "age": "ordinal", "score": "continuous"}},
    )

    assert resp.status_code == 200
    profile = resp.json()["profile"]
    assert profile["columns"]["value"]["type"] == "continuous"
    assert profile["columns"]["age"]["type"] == "ordinal"
    assert resp.json()["profile"]["type_confirmed"] is True

    snapshot_path = root / session_id / "snapshot.json"
    assert snapshot_path.is_file()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    dataset = snapshot["datasets"][0]
    assert dataset["type_confirmed"] is True
    assert dataset["column_types"]["age"] == "ordinal"


def test_batch_column_types_rejects_unknown_column_atomically() -> None:
    """批量：含未知列时整体拒绝（404），不做部分修改。"""
    client, session_id = _client_with_session()
    dataset_id = _upload_two_numeric(client, session_id)

    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"types": {"value": "continuous", "nope": "ordinal"}},
    )

    assert resp.status_code == 404
    assert "nope" in resp.json()["detail"]


def test_batch_column_types_rejects_invalid_type() -> None:
    """批量：含非法类型时整体拒绝（400）。"""
    client, session_id = _client_with_session()
    dataset_id = _upload_two_numeric(client, session_id)

    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"types": {"value": "banana"}},
    )

    assert resp.status_code == 400



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

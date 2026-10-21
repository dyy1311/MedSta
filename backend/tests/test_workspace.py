"""012 多工作区：多数据集上传/激活/按激活工作区执行。"""
import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent, PlanOption, PlanStep
from medsta.session.manager import manager
from medsta.session.service import SessionService


class _FakeGateway:
    def __init__(self) -> None:
        self.last_info = ""

    async def request_structured_stream(self, schema, *, fields, input=None, info=None,
                                        instruct="", on_delta=None):
        self.last_info = info or ""
        return AnalysisPlan(
            message="方案",
            steps=[
                PlanStep(title="描述统计", method="describe", target_columns=["age"],
                         chart_type="none", params={}, rationale="数值列概览")
            ],
            options=[PlanOption(id="confirm", label="按此执行", action="confirm")],
        )


@pytest.fixture()
def service(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=DiscussionAgent(gateway=_FakeGateway()),
                             record_store=store, data_root=tmp_path)
    return service


def test_manager_multiple_datasets() -> None:
    """B1: 同一会话两次上传得到两个不同 dataset_id"""
    session = manager.create_session()
    df1 = pd.DataFrame({"age": [1.0, 2.0]})
    df2 = pd.DataFrame({"age": [3.0, 4.0, 5.0]})
    id1 = manager.attach_dataset(session.session_id, df=df1, name="a.csv")
    id2 = manager.attach_dataset(session.session_id, df=df2, name="b.csv")
    assert id1 != id2
    assert manager.active_data(session.session_id).df is df1  # 首个上传默认激活
    manager.activate(session.session_id, id2)
    assert manager.active_data(session.session_id).df is df2


async def test_service_chat_uses_active_dataset(service, tmp_path) -> None:
    """B2: chat 使用激活工作区的画像与数据"""
    sent, send = _collector()
    sid = service.create_session()
    id1 = service.attach_dataframe(sid, df=pd.DataFrame({"age": [1.0]}), dataset_path="a.csv")
    id2 = service.attach_dataframe(sid, df=pd.DataFrame({"age": [1.0, 2.0, 3.0, 4.0]}), dataset_path="b.csv")
    await service.handle(sid, {"type": "workspace", "dataset_id": id2}, send)
    await service.handle(sid, {"type": "chat", "content": "分析年龄"}, send)
    await service.wait_idle(sid)
    profile_events = [m for m in sent if m["type"] == "data_profile"]
    assert profile_events[-1]["profile"]["row_count"] == 4


async def test_missing_dataset_errors(service) -> None:
    """B3: 未上传 → DATA_REQUIRED；激活不存在的 dataset → INVALID_PARAM"""
    sent, send = _collector()
    sid = service.create_session()
    await service.handle(sid, {"type": "chat", "content": "分析"}, send)
    assert sent[0]["code"] == "DATA_REQUIRED"
    await service.handle(sid, {"type": "workspace", "dataset_id": "nope"}, send)
    errors = [m for m in sent if getattr(m, "get", lambda k: None)("code") == "INVALID_PARAM"]
    assert errors


def _collector():
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    return sent, _send

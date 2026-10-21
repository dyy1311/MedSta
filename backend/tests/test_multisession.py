"""019 B5–B6：多会话隔离与工作区/列类型契约。"""
from __future__ import annotations

import io

from agently.core.storage import LocalRecordStore
import pandas as pd

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent
from medsta.session.manager import manager
from medsta.session.service import SessionService

from tests.conftest import RecordingFakeRequest


PLAN = {
    "message": "先看分布",
    "steps": [
        {
            "title": "描述统计",
            "method": "describe",
            "target_columns": ["value"],
            "chart_type": "none",
            "params": {},
            "rationale": "连续变量首先看分布",
        }
    ],
    "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
}


def _service(tmp_path) -> tuple[SessionService, LocalRecordStore]:
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(
        agent=DiscussionAgent(request_factory=lambda: RecordingFakeRequest(PLAN)),
        record_store=store,
        data_root=tmp_path,
    )
    return service, store


def _collector() -> tuple[list[dict], "object"]:
    sent: list[dict] = []

    async def _send(message: dict) -> None:
        sent.append(message)

    return sent, _send


async def test_two_sessions_keep_plans_and_events_separate(tmp_path) -> None:
    """B5: 两个会话各自讨论，方案/事件/记录互不污染。"""
    service, store = _service(tmp_path)
    sid_a = service.create_session()
    sid_b = service.create_session()
    df = pd.DataFrame({"value": [1.5, 2.5, 3.5, 4.5], "group": ["a", "a", "b", "b"]})
    service.attach_dataframe(sid_a, df=df, dataset_path="a.csv", name="a.csv")
    service.attach_dataframe(sid_b, df=df.head(3), dataset_path="b.csv", name="b.csv")
    manager.get(sid_a).data.type_confirmed = True
    manager.get(sid_b).data.type_confirmed = True

    sent_a, send_a = _collector()
    sent_b, send_b = _collector()
    await service.handle(sid_a, {"type": "chat", "content": "分析 A"}, send_a)
    await service.wait_idle(sid_a)
    await service.handle(sid_b, {"type": "chat", "content": "分析 B"}, send_b)
    await service.wait_idle(sid_b)

    plan_a = [message for message in sent_a if message["type"] == "plan"]
    plan_b = [message for message in sent_b if message["type"] == "plan"]
    assert len(plan_a) == 1 and len(plan_b) == 1
    assert isinstance(manager.get(sid_a).plan, AnalysisPlan)
    assert isinstance(manager.get(sid_b).plan, AnalysisPlan)

    records_a = await store.search(
        filters={"collection": "sessions", "scope.session_id": sid_a}
    )
    records_b = await store.search(
        filters={"collection": "sessions", "scope.session_id": sid_b}
    )
    assert len(records_a) == 1 and len(records_b) == 1

    # 报告缓存按会话分桶：给 A 注入报告后 B 仍为空
    service.reports[sid_a] = {"steps": [{"title": "A"}]}
    assert sid_b not in service.reports


def test_activate_workspace_switches_profile(client, session_id: str) -> None:
    """B6: activate 切换激活表并回传该表画像。"""
    first = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("first.csv", io.BytesIO(b"value\n1.5\n2.5\n3.5\n"), "text/csv")},
    ).json()
    second = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("second.csv", io.BytesIO(b"bp\n120\n130\n"), "text/csv")},
    ).json()

    resp = client.post(f"/sessions/{session_id}/workspace/{second['dataset_id']}/activate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset_id"] == second["dataset_id"]
    assert body["name"] == "second.csv"
    assert list(body["profile"]["columns"]) == ["bp"]
    assert manager.get(session_id).active_dataset_id == second["dataset_id"]
    assert manager.get(session_id).datasets[first["dataset_id"]].df.shape == (3, 1)


def test_patch_column_type_confirms_and_recomputes(client, session_id: str) -> None:
    """B6: PATCH 列类型视为敲定，重算该列统计并置 type_confirmed。"""
    uploaded = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("d.csv", io.BytesIO(b"grade\n1\n2\n3\n4\n"), "text/csv")},
    ).json()
    dataset_id = uploaded["dataset_id"]
    assert uploaded["type_confirmed"] is False

    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"column": "grade", "type": "continuous"},
    )

    assert resp.status_code == 200
    profile = resp.json()["profile"]
    assert profile["columns"]["grade"]["type"] == "continuous"
    assert profile["columns"]["grade"]["stats"]["mean"] == 2.5
    assert profile["type_confirmed"] is True
    assert manager.get(session_id).datasets[dataset_id].type_confirmed is True


def test_patch_column_type_error_paths(client, session_id: str) -> None:
    """B6: 未知工作区/未知列 404；非法类型 400。"""
    uploaded = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("d.csv", io.BytesIO(b"grade\n1\n2\n"), "text/csv")},
    ).json()
    dataset_id = uploaded["dataset_id"]

    assert client.patch(
        f"/sessions/{session_id}/workspace/nope/columns",
        json={"column": "grade", "type": "continuous"},
    ).status_code == 404
    assert client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"column": "nope", "type": "continuous"},
    ).status_code == 404
    resp = client.patch(
        f"/sessions/{session_id}/workspace/{dataset_id}/columns",
        json={"column": "grade", "type": "banana"},
    )
    assert resp.status_code == 400
    assert "非法列类型" in resp.json()["detail"]


def test_activate_unknown_workspace_returns_404(client, session_id: str) -> None:
    """B6: 激活不存在的工作区返回 404。"""
    resp = client.post(f"/sessions/{session_id}/workspace/missing/activate")

    assert resp.status_code == 404
    assert "工作区不存在" in resp.json()["detail"]

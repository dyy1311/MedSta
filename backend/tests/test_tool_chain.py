"""033 B2–B4：手动原子工作链执行通道（run_chain，无模型参与）。"""
from __future__ import annotations

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.agents.discussion import AnalysisPlan
from medsta.session.manager import SessionStatus, manager
from medsta.session.service import SessionService

from tests.helpers import (
    PLAN_TABLE_ONLY,
    collect_until,
    drive_to_review,
    fake_agent,
    upload_csv,
)


def _chain_steps() -> list[dict]:
    return [
        {
            "method": "describe",
            "target_columns": ["value"],
            "chart_type": "histogram",
            "params": {"group_by": "group"},
        },
        {
            "method": "group_compare",
            "target_columns": ["value"],
            "chart_type": "none",
            "params": {"group_column": "group"},
        },
    ]


def _frames_until(ws, target: str, limit: int = 120) -> tuple[list[dict], dict]:
    """收集帧直到目标类型；遇错误帧立即失败（避免服务端等待输入造成死锁）。"""
    frames: list[dict] = []
    for _ in range(limit):
        message = ws.receive_json()
        frames.append(message)
        if message.get("type") == "error":
            raise AssertionError(f"收到错误帧：{message}")
        if message.get("type") == target:
            return frames, message
    raise AssertionError(f"{limit} 帧内未等到 {target}")


def test_run_chain_executes_without_model(client, app, session_id: str) -> None:
    """B2: 手动链全程零模型调用（不设 agent），两步执行并跳过出图确认暂停。"""
    upload_csv(client, session_id)  # 不 set_agent：讨论不可用，装配链不受影响

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "run_chain", "steps": _chain_steps()})
        frames, review = _frames_until(ws, "review_request")

        assert not any(f["type"] == "chart_config" for f in frames)
        assert not any(f["type"] == "type_review" for f in frames)
        assert [s["method"] for s in review["report"]["steps"]] == ["describe", "group_compare"]
        assert review["report"]["steps"][0]["artifact"] is not None  # 装配时已选图

    session = manager.get(session_id)
    assert session is not None
    assert isinstance(session.plan, AnalysisPlan)
    assert session.status.value == "executing"  # 停在审阅等待


def test_run_chain_rejects_invalid_steps(client, app, session_id: str) -> None:
    """B3: 未知方法/缺必填参数 → INVALID_PLAN 错误帧带 issues 明细，不产生执行。"""
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json(
            {
                "type": "run_chain",
                "steps": [
                    {"method": "nope", "target_columns": ["value"],
                     "chart_type": "none", "params": {}}
                ],
            }
        )
        _, unknown = collect_until(ws, {"error"})
        assert unknown["code"] == "INVALID_PLAN"
        assert unknown["detail"]["issues"]

        ws.send_json(
            {
                "type": "run_chain",
                "steps": [
                    {"method": "group_compare", "target_columns": ["value"],
                     "chart_type": "none", "params": {}}
                ],
            }
        )
        _, missing = collect_until(ws, {"error"})
        assert missing["code"] == "INVALID_PLAN"
        assert any("group_column" in i["message"] for i in missing["detail"]["issues"])

    # 校验失败不产生执行、不改状态
    assert manager.get(session_id).status.value == "discussing"


def test_run_chain_allowed_after_delivery(client, app, session_id: str) -> None:
    """B4a: 交付态装配新链可执行（先回 discussing 再执行）。"""
    app.state.service.set_agent(fake_agent(PLAN_TABLE_ONLY))
    upload_csv(client, session_id)
    with client.websocket_connect(f"/ws/{session_id}") as ws:
        drive_to_review(ws)
        ws.send_json({"type": "review", "decision": "accept"})
        collect_until(ws, {"delivered"})

        ws.send_json({"type": "run_chain", "steps": _chain_steps()})
        _, review = _frames_until(ws, "review_request")
        assert len(review["report"]["steps"]) == 2


@pytest.fixture()
def service_env(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    session_id = service.create_session()
    df = pd.DataFrame({"group": ["A", "A", "B", "B"], "value": [1.0, 2.0, 5.0, 6.0]})
    service.attach_dataframe(session_id, df=df, dataset_path="mem.csv")
    manager.get(session_id).data.type_confirmed = True
    return service, session_id


async def test_run_chain_rejected_while_busy(service_env) -> None:
    """B4b: 会话忙（任务进行中）时 run_chain 被 SESSION_BUSY 拒绝。"""
    service, session_id = service_env
    service._busy.add(session_id)
    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    await service.handle(session_id, {"type": "run_chain", "steps": _chain_steps()}, send)

    assert any(m.get("code") == "SESSION_BUSY" for m in sent)

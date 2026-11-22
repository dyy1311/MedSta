"""041 模型辅助列类型确认：证据契约、建议事件、非法建议丢弃。"""
from __future__ import annotations

import pandas as pd
import pytest
from agently.core.storage import LocalRecordStore

from medsta.session.service import SessionService


class FakeAdvisor:
    """假模型替身：记录收到的证据，返回预设建议（真实契约类，含 model_dump）。"""

    def __init__(self, suggestions: list[dict]) -> None:
        from medsta.agents.type_advisor import ColumnTypeSuggestion

        self._suggestions = [ColumnTypeSuggestion(**payload) for payload in suggestions]
        self.evidence: list[dict] | None = None

    def advise(self, evidence: list[dict]):
        self.evidence = evidence
        return self

    @property
    def columns(self):
        return self._suggestions


@pytest.fixture()
def service_env(tmp_path):
    store = LocalRecordStore(root=str(tmp_path / "records"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    session_id = service.create_session()
    df = pd.DataFrame(
        {
            "分组": ["A", "B", "A", "B"],
            "年龄": [25, 31, 42, 28],
            "分期": [1, 2, 3, 4],
        }
    )
    service.attach_dataframe(session_id, df=df, dataset_path="mem.csv")
    return service, session_id


async def _sent(service, session_id, event):
    frames: list[dict] = []

    async def send(message: dict) -> None:
        frames.append(message)

    await service.handle(session_id, event, send)
    return frames


async def test_suggest_column_types_returns_suggestions(service_env) -> None:
    """B1: 建议事件含每列建议+理由；模型收到样本值证据。"""
    service, session_id = service_env
    advisor = FakeAdvisor(
        [
            {"name": "分期", "suggested_type": "ordinal", "confidence": 0.9,
             "reason": "取值 1–4 表示疾病分期等级"},
            {"name": "年龄", "suggested_type": "continuous", "confidence": 0.95,
             "reason": "连续测量指标"},
        ]
    )
    service.type_advisor = advisor

    frames = await _sent(service, session_id, {"type": "suggest_column_types"})

    event = next(f for f in frames if f["type"] == "column_type_suggestions")
    assert {s["name"]: s["suggested_type"] for s in event["suggestions"]} == {
        "分期": "ordinal",
        "年龄": "continuous",
    }
    # 证据契约：列名/推断类型/样本值/缺失数
    names = {item["name"] for item in advisor.evidence}
    assert names == {"分组", "年龄", "分期"}
    staging = next(item for item in advisor.evidence if item["name"] == "分期")
    assert staging["sample_values"]
    assert "inferred_type" in staging and "missing" in staging


async def test_illegal_suggestion_dropped(service_env) -> None:
    """B2: 非法类型建议被宿主丢弃进 skipped，合法建议保留。"""
    service, session_id = service_env
    service.type_advisor = FakeAdvisor(
        [
            {"name": "年龄", "suggested_type": "banana", "confidence": 0.5, "reason": "x"},
            {"name": "分期", "suggested_type": "ordinal", "confidence": 0.9, "reason": "y"},
        ]
    )

    frames = await _sent(service, session_id, {"type": "suggest_column_types"})

    event = next(f for f in frames if f["type"] == "column_type_suggestions")
    assert [s["name"] for s in event["suggestions"]] == ["分期"]
    assert event["skipped"] == ["年龄"]


async def test_suggest_requires_data(service_env, tmp_path) -> None:
    """B3: 未上传数据 → DATA_REQUIRED。"""
    store = LocalRecordStore(root=str(tmp_path / "records2"))
    service = SessionService(agent=None, record_store=store, data_root=tmp_path)
    empty_id = service.create_session()

    frames = await _sent(service, empty_id, {"type": "suggest_column_types"})

    error = next(f for f in frames if f["type"] == "error")
    assert error["code"] == "DATA_REQUIRED"


async def test_suggest_requires_model(service_env) -> None:
    """B4: 模型不可用（未注入 advisor）→ MODEL_UNAVAILABLE。"""
    service, session_id = service_env

    frames = await _sent(service, session_id, {"type": "suggest_column_types"})

    error = next(f for f in frames if f["type"] == "error")
    assert error["code"] == "MODEL_UNAVAILABLE"


async def test_advise_runs_off_event_loop(service_env) -> None:
    """P1: 模型调用（阻塞式 HTTP，默认超时 120s）必须移出事件循环。"""
    import asyncio
    import time as _time

    from medsta.agents.type_advisor import ColumnAdviceReport, ColumnTypeSuggestion

    class SleepyAdvisor:
        def advise(self, evidence):
            _time.sleep(0.15)
            return ColumnAdviceReport(
                columns=[ColumnTypeSuggestion(name="年龄", suggested_type="continuous")]
            )

    service, session_id = service_env
    service.type_advisor = SleepyAdvisor()
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    hb = asyncio.create_task(heartbeat())
    frames = await _sent(service, session_id, {"type": "suggest_column_types"})
    hb.cancel()

    assert any(f["type"] == "column_type_suggestions" for f in frames)
    # 0.15s 阻塞期间循环应保持可调度（阻塞实现 ticks≈0）
    assert ticks >= 4, f"事件循环疑似被阻塞：ticks={ticks}"

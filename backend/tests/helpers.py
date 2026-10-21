"""测试辅助：上传、伪模型方案、WebSocket 帧收集（仅编排，不做断言）。"""
from __future__ import annotations

import io
from typing import Iterable

from medsta.agents.discussion import DiscussionAgent

from tests.conftest import RecordingFakeRequest


CSV = b"group,value,age\nA,1.5,20\nA,2.5,21\nA,3.5,22\nB,4.5,41\nB,5.5,42\nB,6.5,43\n"

PLAN_WITH_CHART = {
    "message": "先描述分布，再出直方图",
    "steps": [
        {
            "title": "分布统计",
            "method": "describe",
            "target_columns": ["value"],
            "chart_type": "histogram",
            "params": {},
            "rationale": "连续变量先看分布",
        }
    ],
    "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
}

PLAN_TABLE_ONLY = {
    "message": "只出统计表",
    "steps": [
        {
            "title": "分布统计",
            "method": "describe",
            "target_columns": ["value"],
            "chart_type": "none",
            "params": {},
            "rationale": "连续变量先看分布",
        }
    ],
    "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
}

PLAN_NO_TABLE = {
    "message": "正态性检验",
    "steps": [
        {
            "title": "A/B 正态性",
            "method": "normality_test",
            "target_columns": ["value"],
            "chart_type": "qq_plot",
            "params": {},
            "rationale": "参数检验前检查正态性",
        }
    ],
    "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
}


def fake_agent(payload: dict) -> DiscussionAgent:
    return DiscussionAgent(request_factory=lambda: RecordingFakeRequest(payload))


def upload_csv(client, session_id: str, content: bytes = CSV, name: str = "cohort.csv") -> dict:
    response = client.post(
        f"/sessions/{session_id}/data",
        files={"file": (name, io.BytesIO(content), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def collect_until(ws, types: Iterable[str], limit: int = 120) -> tuple[list[dict], dict]:
    """读取 WS 帧直到出现目标类型；返回全部帧与命中帧。"""
    wanted = set(types)
    frames: list[dict] = []
    for _ in range(limit):
        message = ws.receive_json()
        frames.append(message)
        if message.get("type") in wanted:
            return frames, message
    raise AssertionError(f"在 {limit} 帧内未收到 {wanted}；最后帧：{frames[-1] if frames else None}")


def drive_to_review(ws, *, types: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """讨论 → 类型确认 → 方案 → 执行 → 审阅；返回全部帧与 review_request。"""
    frames: list[dict] = []

    ws.send_json({"type": "chat", "content": "分析 value 的分布"})
    got, _ = collect_until(ws, {"type_review"})
    frames.extend(got)

    ws.send_json({"type": "type_confirm", "types": types or {"group": "categorical", "value": "continuous", "age": "continuous"}})
    got, _ = collect_until(ws, {"plan"})
    frames.extend(got)

    ws.send_json({"type": "confirm_plan"})
    got, config = collect_until(ws, {"chart_config", "review_request"})
    frames.extend(got)
    if config.get("type") == "chart_config":
        ws.send_json({"type": "chart_choice", "use_default": True, "layout": "separate", "alpha": 0.05, "correction": "holm"})
        got, review = collect_until(ws, {"review_request"})
        frames.extend(got)
    else:
        review = config
    return frames, review

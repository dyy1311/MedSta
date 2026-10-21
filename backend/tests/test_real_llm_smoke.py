"""019 B20：真实模型冒烟（默认跳过，显式开启才消耗额度）。

运行：
    MEDSTA_REAL_LLM=1 pytest tests/test_real_llm_smoke.py -q
前置：项目根 .env 或环境变量含 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。
"""
from __future__ import annotations

import os

import pytest

from medsta.config import ProviderConfig
from medsta.stats.registry import get_tool

from tests.helpers import collect_until, upload_csv


pytestmark = pytest.mark.real_llm

_ENABLED = os.environ.get("MEDSTA_REAL_LLM") == "1"


def _cohort_csv() -> bytes:
    """40 行确定性样本：两组连续值 + 年龄 + 二分类结局。"""
    lines = ["group,value,age,outcome"]
    for index in range(40):
        group = "A" if index < 20 else "B"
        value = round(10 + (index % 5) * 0.5 + (0 if group == "A" else 2), 2)
        age = 30 + index
        outcome = 1 if (index % 3 == 0) else 0
        lines.append(f"{group},{value},{age},{outcome}")
    return ("\n".join(lines) + "\n").encode("utf-8")


@pytest.mark.skipif(not _ENABLED, reason="设置 MEDSTA_REAL_LLM=1 才运行真实模型冒烟")
def test_real_model_plan_and_delivery(client, app, session_id: str) -> None:
    """真实链路：讨论生成合法方案 → 确认 → 执行 → 交付。"""
    try:
        ProviderConfig.from_env()
    except RuntimeError as exc:
        pytest.skip(f"缺少模型配置：{exc}")

    upload_csv(client, session_id, content=_cohort_csv(), name="cohort.csv")

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "请比较 A、B 两组的 value 差异，并说明选择依据"})
        _, type_review = collect_until(ws, {"type_review", "error"}, limit=5)
        if type_review["type"] == "error":
            pytest.fail(f"真实模型链路在类型确认前失败：{type_review}")

        types = {
            column["name"]: "categorical" if column["name"] in ("group", "outcome") else "continuous"
            for column in type_review["columns"]
        }
        ws.send_json({"type": "type_confirm", "types": types})

        _, plan = collect_until(ws, {"plan", "error"}, limit=5000)
        assert plan["type"] == "plan", plan
        assert plan["steps"], "模型未给出任何步骤"
        for step in plan["steps"]:
            assert get_tool(step["method"]) is not None, step
            assert step["target_columns"], step
            assert step["rationale"].strip(), "rationale 是硬要求"

        ws.send_json({"type": "confirm_plan"})
        _, stage = collect_until(ws, {"chart_config", "review_request", "error"}, limit=60)
        if stage["type"] == "error":
            pytest.fail(f"真实模型方案被宿主拒绝：{stage}")
        if stage["type"] == "chart_config":
            ws.send_json({"type": "chart_choice", "use_default": True})
            _, stage = collect_until(ws, {"review_request", "error"}, limit=120)

        assert stage["type"] == "review_request", stage
        assert stage["report"]["steps"], "执行报告为空"

        ws.send_json({"type": "review", "decision": "accept"})
        _, delivered = collect_until(ws, {"delivered"}, limit=30)

    assert delivered["report"]["steps"]

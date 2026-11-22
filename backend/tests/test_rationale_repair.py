"""方案缺 rationale 的自动补全（用户实测：6 个步骤全部报「缺少选择依据」）。

两条防线：
1. 输出契约必须显式列出 `rationale` / `depends_on`（模型第一眼能看到）；
2. 模型仍漏填时，宿主发起一轮「只补依据」的请求再合并；补完仍缺才按硬门拒绝
   （不放弃可解释性，也不让用户对着无从修改的错误发呆）。
"""
from __future__ import annotations

import pandas as pd
import pytest

from medsta.agents.discussion import _OUTPUT_FIELDS, AnalysisPlan, DiscussionAgent
from medsta.data.profiler import profile_dataframe
from medsta.errors import ToolValidationError


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {"group": ["A", "A", "B", "B"], "value": [1.0, 2.0, 3.0, 4.0], "age": [40, 41, 50, 51]}
    )


def _step_payload(rationale: str) -> dict:
    return {
        "title": "分布统计",
        "method": "describe",
        "target_columns": ["value"],
        "chart_type": "none",
        "params": {},
        "rationale": rationale,
    }


def _plan_payload(rationale: str, steps: int = 2) -> dict:
    return {
        "message": "先看分布",
        "steps": [_step_payload(rationale) for _ in range(steps)],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }


class _ScriptedRequest:
    """按脚本返回固定 payload 的模型替身（每次 start 返回下一份）。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def input(self, value):
        return self

    def info(self, value):
        return self

    def instruct(self, value):
        return self

    def output(self, fields, **kwargs):
        return self

    def start(self):
        return self._payload


def test_output_fields_declare_rationale_and_depends_on() -> None:
    """契约防线：steps 字段描述必须点名 rationale（必填）与 depends_on。"""
    description = _OUTPUT_FIELDS["steps"][1]

    assert "rationale" in description
    assert "必填" in description
    assert "depends_on" in description


def test_missing_rationale_is_repaired_before_validation() -> None:
    """补全防线：第一版漏填依据 → 自动补一轮 → 方案通过且依据非空。"""
    payloads = iter([_plan_payload(""), _plan_payload("连续变量先看分布形态")])
    calls: list[str] = []

    def factory():
        payload = next(payloads)
        calls.append(payload["steps"][0]["rationale"])
        return _ScriptedRequest(payload)

    agent = DiscussionAgent(request_factory=factory)
    plan = agent.draft_plan(profile_dataframe(_df()), "分析 value 的分布")

    assert isinstance(plan, AnalysisPlan)
    assert all(step.rationale.strip() for step in plan.steps)
    assert len(calls) == 2, "只补一轮：第一版 + 补依据版"


def test_repair_failure_keeps_hard_gate() -> None:
    """补完仍缺 → 仍按硬门拒绝（可解释性不降级）。"""
    payloads = iter([_plan_payload(""), _plan_payload("")])

    agent = DiscussionAgent(request_factory=lambda: _ScriptedRequest(next(payloads)))

    with pytest.raises(ToolValidationError) as excinfo:
        agent.draft_plan(profile_dataframe(_df()), "分析 value 的分布")

    assert any(issue.code == "MISSING_PARAM" for issue in excinfo.value.issues)


def test_no_repair_call_when_rationale_present() -> None:
    """依据齐全时不额外调用模型（省一次往返）。"""
    calls: list[int] = []

    def factory():
        calls.append(1)
        return _ScriptedRequest(_plan_payload("连续变量先看分布形态"))

    agent = DiscussionAgent(request_factory=factory)
    plan = agent.draft_plan(profile_dataframe(_df()), "分析 value 的分布")

    assert plan.steps and len(calls) == 1

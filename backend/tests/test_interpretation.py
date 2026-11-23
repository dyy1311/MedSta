"""结果解释：证据白名单、因果守卫、句数截断与降级行为（spec 022）。"""
from __future__ import annotations

import copy
import json

import pandas as pd
import pytest

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.agents.interpretation import (
    ESTIMAND_DECLARED_CAVEAT,
    EXPLORATORY_CAVEAT,
    InterpretationAgent,
    _unverified_numbers,
    build_evidence,
)
from medsta.config import InterpretConfig
from medsta.data.profiler import profile_dataframe
from tests.conftest import RecordingFakeRequest


def make_plan() -> AnalysisPlan:
    return AnalysisPlan(
        message="比较两组连续变量的差异",
        steps=[
            PlanStep(
                step_id="step_1",
                title="两组比较",
                method="group_compare",
                target_columns=["value"],
                chart_type="boxplot",
                params={"group_column": "group", "test": "auto"},
                rationale="连续变量、两组比较；非正态时降级为秩检验",
            )
        ],
    )


def make_report() -> dict:
    return {
        "steps": [
            {
                "title": "两组比较",
                "method": "group_compare",
                "status": "success",
                "result": {
                    "column": "value",
                    "group_column": "group",
                    "test": "welch_t",
                    "statistic": 5.12,
                    "p_value": 0.0028,
                    "mean_diff": 10.0,
                    "ci95": [4.4, 15.6],
                    "cohens_d": 1.9,
                    "groups": {"A": 6, "B": 6},
                    "strategy": {"steps": ["正态性检验 p<0.05"], "final_method": "welch_t"},
                    "raw_rows": [[1, 2], [3, 4]],
                    "table": {"columns": ["a"], "rows": [{"a": 1}]},
                },
                "artifact": None,
                "table": {"columns": ["a"], "rows": [{"a": 1}]},
                "error": None,
            }
        ]
    }


ALLOWED_GROUP_COMPARE = {
    "test",
    "statistic",
    "p_value",
    "mean_diff",
    "ci95",
    "cohens_d",
    "final_method",
    "groups",
}


def test_evidence_uses_whitelist_only(sample_df: pd.DataFrame) -> None:
    profile = profile_dataframe(sample_df)

    evidence = build_evidence(make_report(), make_plan(), profile)

    payload = json.dumps(evidence, ensure_ascii=False, default=str)
    assert "raw_rows" not in payload
    assert "[1, 2]" not in payload

    step = evidence["steps"][0]
    assert step["ref"] == "S1"
    assert step["method"] == "group_compare"
    assert set(step["values"]) == ALLOWED_GROUP_COMPARE
    assert step["values"]["p_value"] == pytest.approx(0.0028)
    assert step["values"]["final_method"] == "welch_t"
    assert step["values"]["groups"] == {"A": 6, "B": 6}
    assert evidence["profile"]["rows"] == len(sample_df)
    assert evidence["profile"]["types"]["value"] == "continuous"


def make_payload(finding: str, *, summary: str = "两组差异有统计学意义") -> dict:
    return {
        "summary": summary,
        "steps": [{"step_index": 0, "finding": finding, "caveat": ""}],
        "caveats": [],
    }


def make_agent(payloads: list[dict]):
    """按调用顺序回放 payload；用尽后重复最后一个。"""
    calls = {"count": 0}

    def factory() -> RecordingFakeRequest:
        index = min(calls["count"], len(payloads) - 1)
        calls["count"] += 1
        return RecordingFakeRequest(payloads[index])

    return InterpretationAgent(request_factory=factory), calls


def test_causal_claim_rejected_after_retry(sample_df: pd.DataFrame) -> None:
    bad = make_payload("治疗组导致结局改善，p=0.003。")
    agent, calls = make_agent([bad, bad])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is None
    assert calls["count"] == 2


def test_negated_causality_is_allowed(sample_df: pd.DataFrame) -> None:
    good = make_payload("两组差异有统计学意义，但不能说明存在因果关系（p=0.003）。")
    agent, calls = make_agent([good])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is not None
    assert "因果关系" in result.steps[0].finding
    assert calls["count"] == 1


def test_sentence_cap_truncates_at_sentence_boundary(sample_df: pd.DataFrame) -> None:
    payload = make_payload("第一句。第二句。第三句。")
    agent, _ = make_agent([payload])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=2),
    )

    assert result is not None
    assert result.steps[0].finding == "第一句。第二句。"


def test_max_sentences_is_clamped() -> None:
    assert InterpretConfig(max_sentences=0).max_sentences == 1
    assert InterpretConfig(max_sentences=99).max_sentences == 5
    assert InterpretConfig(max_sentences=3).max_sentences == 3


def test_out_of_range_step_index_dropped(sample_df: pd.DataFrame) -> None:
    payload = {
        "summary": "整体差异有统计学意义",
        "steps": [
            {"step_index": 0, "finding": "两组差异明显（p=0.003）。", "caveat": ""},
            {"step_index": 7, "finding": "越界步骤的结论。", "caveat": ""},
        ],
        "caveats": [],
    }
    agent, _ = make_agent([payload])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is not None
    assert [item.step_index for item in result.steps] == [0]
    assert "越界" not in result.steps[0].finding


def test_all_out_of_range_returns_none(sample_df: pd.DataFrame) -> None:
    payload = {
        "summary": "整体差异有统计学意义",
        "steps": [{"step_index": 7, "finding": "越界步骤的结论。", "caveat": ""}],
        "caveats": [],
    }
    agent, _ = make_agent([payload])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is None


def test_rounding_and_inequality_not_flagged() -> None:
    allowed = {round(0.0287, digits) for digits in range(4)}

    assert _unverified_numbers("p=0.029", allowed) == []
    assert _unverified_numbers("p<0.001", allowed) == []
    assert _unverified_numbers("效应量 0.03", allowed) == []


def test_invented_number_flagged_not_rejected(sample_df: pd.DataFrame) -> None:
    payload = make_payload("两组差异为 42.7 分（p=0.003）。")
    agent, _ = make_agent([payload])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is not None
    assert result.unverified_numbers == ["42.7"]


def test_caveat_switches_when_estimand_declared(sample_df: pd.DataFrame) -> None:
    """029 B11: 已声明估计目标时用对应文案，且不与探索性文案叠加。"""
    from medsta.agents.discussion import EstimandSpec

    plan = make_plan().model_copy(
        update={
            "estimand": EstimandSpec(
                population="成人",
                variable="评分",
                treatment="A vs B",
                summary_measure="均值差",
            )
        }
    )
    agent, _ = make_agent([make_payload("两组差异有统计学意义（p=0.003）。")])

    result = agent.interpret(
        report=make_report(),
        plan=plan,
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is not None
    assert result.caveats[-1] == ESTIMAND_DECLARED_CAVEAT
    assert EXPLORATORY_CAVEAT not in result.caveats


def test_caveat_is_exploratory_without_estimand(sample_df: pd.DataFrame) -> None:
    """029 B11: 未声明估计目标时用探索性文案。"""
    agent, _ = make_agent([make_payload("两组差异有统计学意义（p=0.003）。")])

    result = agent.interpret(
        report=make_report(),
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert result is not None
    assert result.caveats[-1] == EXPLORATORY_CAVEAT
    assert ESTIMAND_DECLARED_CAVEAT not in result.caveats


def test_report_steps_untouched(sample_df: pd.DataFrame) -> None:
    report = make_report()
    snapshot = copy.deepcopy(report)
    agent, _ = make_agent([make_payload("两组差异明显（p=0.003）。")])

    agent.interpret(
        report=report,
        plan=make_plan(),
        profile=profile_dataframe(sample_df),
        config=InterpretConfig(max_sentences=1),
    )

    assert report == snapshot


def test_model_failure_returns_none(sample_df: pd.DataFrame) -> None:
    def factory() -> RecordingFakeRequest:
        raise RuntimeError("transport down")

    agent = InterpretationAgent(request_factory=factory)

    assert (
        agent.interpret(
            report=make_report(),
            plan=make_plan(),
            profile=profile_dataframe(sample_df),
            config=InterpretConfig(max_sentences=1),
        )
        is None
    )

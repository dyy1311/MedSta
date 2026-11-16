"""025 B8–B13：析因设计与重复测量方差分析。

教材只在练习题与设计章节提及这两类设计，无公式；本文件以平方和恒等式与
statsmodels（anova_lm / AnovaRM）作为基准。
"""
from __future__ import annotations

import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.inference import factorial_anova, repeated_measures_anova


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 步骤",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="设计类方法口径校验",
    )


def _factorial_frame(*, interaction: float = 0.0, unbalanced: bool = False) -> pd.DataFrame:
    sizes = {"a1": {"b1": 4, "b2": 5, "b3": 6}, "a2": {"b1": 5, "b2": 4, "b3": 6}}
    rows = []
    for a_index, a_level in enumerate(("a1", "a2")):
        for b_index, b_level in enumerate(("b1", "b2", "b3")):
            size = sizes[a_level][b_level] if unbalanced else 4
            base = 3.0 * a_index + 1.0 * b_index
            extra = interaction if (a_level == "a2" and b_level == "b3") else 0.0
            for index in range(size):
                rows.append(
                    {
                        "fa": a_level,
                        "fb": b_level,
                        "y": base + extra + 0.2 * index,
                    }
                )
    return pd.DataFrame(rows)


def test_factorial_ss_identity() -> None:
    """B8: 平衡析因设计满足 SS总=SS(A)+SS(B)+SS(AB)+SS误差。"""
    frame = _factorial_frame()
    step = _step("factorial_anova", ["y"], factor_a="fa", factor_b="fb")

    result = factorial_anova(frame, step, step.params)

    assert result["ss_total"] == pytest.approx(
        result["ss_a"] + result["ss_b"] + result["ss_ab"] + result["ss_error"], rel=1e-9
    )
    assert result["df_a"] == 1
    assert result["df_b"] == 2
    assert result["df_ab"] == 2
    assert result["df_error"] == 18
    assert result["ss_type"] == "balanced"
    assert {row["source"] for row in result["table"]["rows"]} == {
        "A", "B", "A×B", "误差", "总"
    }


def test_factorial_interaction_hint() -> None:
    """B9: 交互显著时提示主效应解释需谨慎。"""
    frame = _factorial_frame(interaction=8.0)
    step = _step("factorial_anova", ["y"], factor_a="fa", factor_b="fb")

    result = factorial_anova(frame, step, step.params)

    assert result["p_ab"] < 0.05
    assert any("交互" in item for item in result["strategy"]["steps"])
    assert "主效应" in " ".join(result["strategy"]["steps"])


def test_factorial_unbalanced_uses_type_two() -> None:
    """B10: 不平衡设计改用 Type II 平方和并说明。"""
    frame = _factorial_frame(unbalanced=True)
    step = _step("factorial_anova", ["y"], factor_a="fa", factor_b="fb")

    result = factorial_anova(frame, step, step.params)

    assert result["ss_type"] == 2
    assert any("Type II" in item or "不平衡" in item for item in result["strategy"]["steps"])
    assert 0.0 <= result["p_a"] <= 1.0
    assert 0.0 <= result["p_ab"] <= 1.0


def _repeated_frame(*, unbalanced: bool = False) -> pd.DataFrame:
    rows = []
    for subject in range(1, 9):
        for index, time_point in enumerate(("t1", "t2", "t3")):
            if unbalanced and subject == 1 and time_point == "t3":
                continue
            rows.append(
                {
                    "subject": f"s{subject}",
                    "time": time_point,
                    "score": 10.0 + 2.0 * index + 0.5 * (subject % 3) + 0.4 * ((subject * (index + 1)) % 3),
                }
            )
    return pd.DataFrame(rows)


def test_repeated_measures_ss_identity() -> None:
    """B11: SS总=SS时间+SS受试者+SS误差，时间效应可检验。"""
    frame = _repeated_frame()
    step = _step("repeated_measures_anova", ["score"], subject_column="subject", within_column="time")

    result = repeated_measures_anova(frame, step, step.params)

    assert result["ss_total"] == pytest.approx(
        result["ss_time"] + result["ss_subject"] + result["ss_error"], rel=1e-9
    )
    assert result["df_time"] == 2
    assert result["df_subject"] == 7
    assert result["df_error"] == 14
    assert 0.0 <= result["p_time"] <= 1.0
    assert result["f_time"] > 0


def test_repeated_measures_rejects_unbalanced() -> None:
    """B12: 受试者×水平缺失时报可读错误并提示改用混合模型。"""
    frame = _repeated_frame(unbalanced=True)
    step = _step("repeated_measures_anova", ["score"], subject_column="subject", within_column="time")

    with pytest.raises(ValueError) as excinfo:
        repeated_measures_anova(frame, step, step.params)

    assert "混合模型" in str(excinfo.value) or "缺失" in str(excinfo.value)


def test_repeated_measures_flags_sphericity() -> None:
    """B13: 明确标注未做球形性校正。"""
    frame = _repeated_frame()
    step = _step("repeated_measures_anova", ["score"], subject_column="subject", within_column="time")

    result = repeated_measures_anova(frame, step, step.params)

    assert result["sphericity_corrected"] is False
    assert "球形" in result["method_note"]
    assert any("球形" in item for item in result["strategy"]["steps"])

"""025 B14–B17：样本量与检验效能（设计期工具，不依赖数据列）。"""
from __future__ import annotations

import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.inference import sample_size
from medsta.stats.registry import execute_step, validate_step


def _step(**params) -> PlanStep:
    return PlanStep(
        title="样本量估计",
        method="sample_size",
        target_columns=[],
        chart_type="none",
        params=params,
        rationale="设计期样本量估计",
    )


def test_two_means_sample_size_matches_reference_table() -> None:
    """B14: α=0.05、power=0.8 时 d=0.5/0.8/1.0 → 每组 64/26/17。"""
    for effect_size, expected in ((0.5, 64), (0.8, 26), (1.0, 17)):
        step = _step(design="two_means", effect_size=effect_size, alpha=0.05, power=0.8)

        result = sample_size(None, step, step.params)

        assert result["n_per_group"] == expected
        assert result["total_n"] == expected * 2
        assert result["solve"] == "n"


@pytest.mark.parametrize(
    ("design", "extra"),
    [
        ("one_mean", {}),
        ("two_means", {}),
        ("paired_means", {}),
        ("two_proportions", {}),
        ("anova", {"k_groups": 3}),
        ("correlation", {}),
    ],
)
def test_six_designs_supported(design: str, extra: dict) -> None:
    """B15: 六种设计均可求解样本量。"""
    step = _step(design=design, effect_size=0.5, alpha=0.05, power=0.8, **extra)

    result = sample_size(None, step, step.params)

    assert result["design"] == design
    assert result["n_per_group"] >= 2
    assert 0.0 < result["power"] <= 1.0
    assert result["formula"]


def test_solve_for_power() -> None:
    """B16: 给定样本量反解检验效能。"""
    step = _step(
        design="two_means", solve="power", effect_size=0.5, alpha=0.05, n=64
    )

    result = sample_size(None, step, step.params)

    assert result["solve"] == "power"
    assert 0.75 < result["power"] < 0.85


def test_effect_size_from_delta_and_sigma() -> None:
    """B15: 未给标准化效应量时由 delta/sigma 换算。"""
    step = _step(design="two_means", delta=5.0, sigma=10.0, alpha=0.05, power=0.8)

    result = sample_size(None, step, step.params)

    assert result["effect_size"] == pytest.approx(0.5, rel=1e-9)
    assert result["n_per_group"] == 64


def test_missing_effect_size_raises() -> None:
    """B15: 既无 effect_size 也无 delta/sigma 时报可读错误。"""
    step = _step(design="two_means", alpha=0.05, power=0.8)

    with pytest.raises(ValueError) as excinfo:
        sample_size(None, step, step.params)

    assert "effect_size" in str(excinfo.value)


def test_sample_size_runs_without_target_columns(tmp_path) -> None:
    """B17: 设计期工具不依赖数据列，校验与执行都应放行。"""
    step = _step(design="two_means", effect_size=0.5, alpha=0.05, power=0.8)
    frame = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]})

    issues = validate_step(step, frame)
    assert [issue for issue in issues if issue.code == "INVALID_PARAM"] == []

    result, artifact = execute_step(frame, step, tmp_path, 0)

    assert artifact is None
    assert result["n_per_group"] == 64
    assert result["method_note"]

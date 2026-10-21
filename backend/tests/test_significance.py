"""019 B10：显著性判定与多重比较校正。"""
from __future__ import annotations

import pytest

from medsta.stats.significance import attach_significance, p_adjust, significance_label


@pytest.mark.parametrize(
    ("p_value", "stars", "significant"),
    [
        (0.0001, "***", True),
        (0.005, "**", True),
        (0.03, "*", True),
        (0.05, "ns", False),
        (0.20, "ns", False),
    ],
)
def test_significance_label_thresholds(p_value, stars, significant) -> None:
    """B10: 星号按常规阈值，significant 按 α 判定。"""
    label = significance_label(p_value, alpha=0.05)

    assert label == {"significant": significant, "stars": stars}


def test_significance_label_uses_user_alpha_for_decision_only() -> None:
    """B10: 放宽 α 时 significant 可翻转，星号仍沿用期刊惯例阈值。"""
    label = significance_label(0.08, alpha=0.10)

    assert label["significant"] is True
    assert label["stars"] == "ns"


def test_significance_label_handles_missing_and_nan() -> None:
    """B10: None/NaN 不崩溃，统一判为不显著。"""
    assert significance_label(None)["stars"] == "ns"
    assert significance_label(float("nan"))["significant"] is False


def test_holm_adjust_is_monotone_and_controls_family_error() -> None:
    """B10: Holm 校正结果 ≥ 原始 p、按原始顺序排列、不超过 1。"""
    raw = [0.01, 0.02, 0.03, 0.20]

    adjusted = p_adjust(raw, "holm")

    assert adjusted == pytest.approx([0.04, 0.06, 0.06, 0.20])
    assert all(adj >= original for adj, original in zip(adjusted, raw))
    assert all(adj <= 1.0 for adj in adjusted)


def test_bonferroni_scales_by_family_size() -> None:
    """B10: Bonferroni = p × 检验数（封顶 1）。"""
    raw = [0.01, 0.02, 0.6]

    adjusted = p_adjust(raw, "bonferroni")

    assert adjusted == pytest.approx([0.03, 0.06, 1.0])


def test_none_and_empty_are_identity() -> None:
    """B10: 不校正时原样返回；空列表不报错。"""
    assert p_adjust([0.01, 0.5], "none") == [0.01, 0.5]
    assert p_adjust([], "holm") == []


def test_unknown_correction_is_rejected() -> None:
    """B10: 未知校正方法显式报错，避免静默放过。"""
    with pytest.raises(ValueError, match="未知校正方法"):
        p_adjust([0.01, 0.02], "magic")


def test_attach_significance_mutates_result() -> None:
    """B10: 结果字典就地补 alpha/significant/stars，供前端直接渲染。"""
    result = {"p_value": 0.032}

    assert attach_significance(result, "p_value", 0.05) is result
    assert result["alpha"] == 0.05
    assert result["significant"] is True
    assert result["stars"] == "*"

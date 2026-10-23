"""028 B1–B4：缺失报告的模式分类、分组差异提示与阈值警告。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats import methods


def _step(targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title="缺失报告",
        method="missing_report",
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="缺失诊断",
    )


def test_missing_pattern_and_complete_rows() -> None:
    """B1: 输出逐列缺失模式与完整行比例。"""
    frame = pd.DataFrame(
        {
            "x": [1.0, np.nan, 3.0, 4.0, 5.0],
            "y": [1.0, np.nan, np.nan, 4.0, 5.0],
        }
    )
    step = _step(["x", "y"])

    result = methods.missing_report(frame, step, step.params)

    assert result["row_count"] == 5
    assert result["complete_rows"] == 3
    assert result["complete_pct"] == pytest.approx(60.0, abs=1e-6)
    assert result["columns"]["x"]["missing"] == 1
    assert result["columns"]["y"]["missing"] == 2
    # x 的缺失位置 {1} 是 y 的缺失位置 {1,2} 的子集 → 单调缺失
    assert result["pattern"] == "monotonic"


def test_missing_pattern_univariate() -> None:
    """B1: 只有一列缺失时判为单变量缺失。"""
    frame = pd.DataFrame({"x": [1.0, np.nan, 3.0], "y": [1.0, 2.0, 3.0]})

    result = methods.missing_report(frame, _step(["x", "y"]), {})

    assert result["pattern"] == "univariate"


def test_missing_pattern_arbitrary() -> None:
    """B1: 缺失位置互不包含时判为任意缺失。"""
    frame = pd.DataFrame(
        {
            "x": [np.nan, 2.0, 3.0, 4.0],
            "y": [1.0, np.nan, 3.0, 4.0],
        }
    )

    result = methods.missing_report(frame, _step(["x", "y"]), {})

    assert result["pattern"] == "arbitrary"


def test_group_missing_difference_hint() -> None:
    """B2: 缺失率在组间差异显著时给出机制提示。"""
    frame = pd.DataFrame(
        {
            "group": ["A"] * 20 + ["B"] * 20,
            "value": [np.nan] * 10 + [1.0] * 10 + [2.0] * 20,
        }
    )

    result = methods.missing_report(frame, _step(["value"], group_by="group"), {"group_by": "group"})

    hint = result["mechanism_hint"]
    assert hint["kind"] == "group_related"
    assert hint["p_value"] < 0.05
    assert "分组" in hint["detail"]


def test_no_hint_when_missing_balanced() -> None:
    """B2: 组间缺失率相近时不给机制提示。"""
    frame = pd.DataFrame(
        {
            "group": ["A"] * 20 + ["B"] * 20,
            "value": [np.nan] * 5 + [1.0] * 15 + [np.nan] * 5 + [2.0] * 15,
        }
    )

    result = methods.missing_report(frame, _step(["value"], group_by="group"), {"group_by": "group"})

    assert result["mechanism_hint"]["kind"] == "inconclusive"


def test_threshold_warnings() -> None:
    """B3: 单列缺失 >50% 与完整行 <10% 给不同警告。"""
    frame = pd.DataFrame(
        {
            "a": [np.nan] * 9 + [1.0],
            "b": [np.nan] * 5 + [2.0] * 4 + [np.nan],
        }
    )

    result = methods.missing_report(frame, _step(["a", "b"]), {})

    warnings = " ".join(result["warnings"])
    assert "删除该列" in warnings
    assert "完整病例" in warnings


def test_mechanism_disclaimer_present() -> None:
    """B4: 明确声明不能仅凭数据断定缺失机制。"""
    frame = pd.DataFrame({"x": [1.0, np.nan, 3.0]})

    result = methods.missing_report(frame, _step(["x"]), {})

    assert "MCAR" in result["mechanism_hint"]["disclaimer"]
    assert "cannot" not in result["mechanism_hint"]["disclaimer"].lower()
    assert result["method_note"]


def test_no_missing_returns_none_pattern() -> None:
    """B1: 无缺失时 pattern=none 且不给机制提示。"""
    frame = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [4.0, 5.0, 6.0]})

    result = methods.missing_report(frame, _step(["x", "y"]), {})

    assert result["pattern"] == "none"
    assert result["mechanism_hint"]["kind"] == "inconclusive"
    assert result["warnings"] == []

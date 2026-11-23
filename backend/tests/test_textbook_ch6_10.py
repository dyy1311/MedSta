"""024 教材第六至十章例题回归：t 检验、方差分析、χ²、秩和。

数值基准来自《医学统计学》第 8 版（李康、贺佳）。
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats import methods

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

# 例 7-4：两种饲料喂养小白鼠 4 周体重增加量（g）
EXAMPLE_7_4_HIGH = np.array([50, 47, 42, 43, 39, 51, 43, 48, 51, 42, 50, 43], dtype=float)
EXAMPLE_7_4_LOW = np.array([36, 38, 37, 38, 36, 39, 37, 35, 33, 37, 39, 36, 34], dtype=float)


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 步骤",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="教材口径校验",
    )


def test_f_variance_matches_example_7_4() -> None:
    """B1: F = S²大/S²小 = 17.659/3.269 = 5.402，α=0.10 判方差不齐。"""
    groups = [("高蛋白", EXAMPLE_7_4_HIGH), ("低蛋白", EXAMPLE_7_4_LOW)]

    homogeneous, steps, detail = methods._f_variance_test(groups, alpha=0.10)

    assert detail["f_value"] == pytest.approx(5.402, abs=0.01)
    assert detail["df1"] == 11
    assert detail["df2"] == 12
    assert homogeneous is False
    assert any("F 检验" in item for item in steps)


def test_paired_skips_variance_test() -> None:
    """B2: 配对设计不做方差齐性检验（教材 §7 注意事项 2）。"""
    before = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0])
    diff = np.array([-0.5, -0.3, -0.1, 0.1, 0.3, 0.5, -0.2, 0.2, 0.0, 0.4])
    df = pd.DataFrame(
        {
            "group": ["before"] * 10 + ["after"] * 10,
            "value": list(before) + list(before + diff),
        }
    )
    step = _step("group_compare", ["value"], group_column="group", paired=True)

    result = methods.group_compare(df, step, step.params)
    trace = "；".join(result["strategy"]["steps"])

    assert "Levene" not in trace
    assert "配对" in trace and "方差齐" in trace


def test_one_sample_t_matches_example_7_1() -> None:
    """B3: 例 7-1（n=35、x̄=3.42、S=0.40、μ0=3.30）→ t=1.77，P>0.05。"""
    from medsta.stats.inference import one_sample_test

    z = np.linspace(-2.0, 2.0, 35)
    z = (z - z.mean()) / z.std(ddof=1)
    values = 3.42 + 0.40 * z
    df = pd.DataFrame({"birth_weight": values})
    step = _step("one_sample_test", ["birth_weight"], mu0=3.30)

    result = one_sample_test(df, step, step.params)

    assert result["test"] == "t"
    assert result["statistic"] == pytest.approx(1.775, abs=0.01)
    assert result["df"] == 34
    assert result["p_value"] > 0.05
    assert result["ci95"][0] == pytest.approx(3.283, abs=0.01)
    assert result["ci95"][1] == pytest.approx(3.557, abs=0.01)


def _mcnemar_frame(a: int, b: int, c: int, d: int) -> pd.DataFrame:
    """构造配对四格表长数据：行=方法 A，列=方法 B。"""
    pairs = [(1, 1)] * a + [(1, 0)] * b + [(0, 1)] * c + [(0, 0)] * d
    return pd.DataFrame(pairs, columns=["method_a", "method_b"])


def test_mcnemar_matches_example_9_4() -> None:
    """B13: 例 9-4（a=48,b=24,c=20,d=106）→ χ²=(24−20)²/44=0.364，P>0.05。"""
    from medsta.stats.inference import mcnemar_test

    frame = _mcnemar_frame(48, 24, 20, 106)
    step = _step("mcnemar_test", ["method_a", "method_b"], row_column="method_a", col_column="method_b")

    result = mcnemar_test(frame, step, step.params)

    assert result["chi2"] == pytest.approx(0.364, abs=0.001)
    assert result["b"] == 24
    assert result["c"] == 20
    assert result["corrected"] is False
    assert result["p_value"] > 0.05


def test_rxc_matches_example_9_5() -> None:
    """B16: 例 9-5 三种疗法有效率 → χ²=22.809，ν=2。"""
    frame = pd.DataFrame(
        {
            "group": ["西药"] * 100 + ["中药"] * 80 + ["中西药"] * 74,
            "effect": ["有效"] * 51 + ["无效"] * 49
            + ["有效"] * 35 + ["无效"] * 45
            + ["有效"] * 59 + ["无效"] * 15,
        }
    )
    step = _step("chi_square", ["group", "effect"])

    result = methods.chi_square(frame, step, step.params)

    assert result["chi2"] == pytest.approx(22.809, abs=0.01)
    assert result["dof"] == 2
    assert result["p_value"] < 0.05


def test_kendall_tau_reported() -> None:
    """B18: Kendall τ-b 与 scipy 一致，含 ties 校正，强度分档沿用 023。"""
    from scipy import stats as sp_stats

    frame = pd.DataFrame(
        {
            "height": [170, 173, 160, 155, 173, 188, 178, 183, 180, 165, 166],
            "forearm": [47, 42, 44, 41, 47, 50, 47, 46, 49, 43, 44],
        }
    )
    step = _step("correlation", ["height", "forearm"], method="kendall")

    result = methods.correlation(frame, step, step.params)
    pair = result["pairs"]["height_forearm"]
    expected = sp_stats.kendalltau(frame["height"], frame["forearm"])

    assert result["method"] == "kendall"
    assert pair["r"] == pytest.approx(float(expected.statistic), rel=1e-9)
    assert pair["p_value"] == pytest.approx(float(expected.pvalue), rel=1e-9)
    assert pair["strength"] in ("较高", "很高")
    assert "Kendall" in result["method_note"]


def test_baseline_fixture_runs_group_compare() -> None:
    """B20: 真实基线夹具可直接用于多组比较，不依赖 docs 路径。"""
    frame = pd.read_csv(FIXTURES / "baseline_sample.csv", encoding="utf-8-sig")

    assert frame.shape[0] == 60
    assert set(frame["手术方式"].unique()) == {0, 1, 2, 3, 4}

    step = _step("anova", ["年龄"], group_column="手术方式")
    result = methods.anova(frame, step, step.params)

    assert result["p_value"] >= 0.0
    assert result["groups"]

"""027 B10–B15：Cox 比例风险回归、Schoenfeld 检查与 RMST。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from statsmodels.duration.hazard_regression import PHReg

from medsta.stats.survival import cox_fit, rmst


def _frame(seed: int = 27, n: int = 80):
    rng = np.random.default_rng(seed)
    time = rng.exponential(12.0, n) + 1.0
    event = (rng.random(n) > 0.3).astype(int)
    covariates = pd.DataFrame(
        {
            "age": rng.normal(0, 1, n),
            "chemo": (rng.random(n) > 0.5).astype(float),
        }
    )
    return time, event, covariates


def test_cox_matches_phreg() -> None:
    """B10: β、HR 与 HR 的 95%CI 与 PHReg 直接调用一致。"""
    time, event, covariates = _frame()

    result = cox_fit(time, event, covariates)

    model = PHReg(time, covariates.to_numpy(), status=event, ties="efron").fit()
    interval = model.conf_int()
    for index, term in enumerate(covariates.columns):
        row = result["coefficients"][index]
        assert row["term"] == term
        assert row["coef"] == pytest.approx(float(model.params[index]), rel=1e-6)
        assert row["se"] == pytest.approx(float(model.bse[index]), rel=1e-6)
        assert row["hr"] == pytest.approx(float(np.exp(model.params[index])), rel=1e-6)
        assert row["hr_ci_low"] == pytest.approx(float(np.exp(interval[index][0])), rel=1e-6)
        assert row["hr_ci_high"] == pytest.approx(float(np.exp(interval[index][1])), rel=1e-6)


def test_cox_likelihood_ratio_test() -> None:
    """B11: 整体 LR 检验 = 2×(llf_full − llf_null)。"""
    time, event, covariates = _frame()

    result = cox_fit(time, event, covariates)

    full = PHReg(time, covariates.to_numpy(), status=event, ties="efron").fit()
    null = PHReg(time, np.ones((len(time), 1)), status=event, ties="efron").fit()
    expected = 2 * (full.llf - null.llf)

    assert result["lr_test"]["chi2"] == pytest.approx(float(expected), rel=1e-6)
    assert result["lr_test"]["df"] == covariates.shape[1]
    assert 0.0 <= result["lr_test"]["p_value"] <= 1.0


def test_cox_wald_test_per_term() -> None:
    """B12: 每个协变量输出 Wald χ² 与 p。"""
    time, event, covariates = _frame()

    result = cox_fit(time, event, covariates)

    model = PHReg(time, covariates.to_numpy(), status=event, ties="efron").fit()
    for index, row in enumerate(result["coefficients"]):
        expected = (float(model.params[index]) / float(model.bse[index])) ** 2
        assert row["wald_chi2"] == pytest.approx(expected, rel=1e-6)
        assert row["p_value"] == pytest.approx(float(model.pvalues[index]), rel=1e-6)


def test_cox_score_test_reported_or_explained() -> None:
    """B13: Score 检验可用时输出，不可用时明确说明，不伪造数值。"""
    time, event, covariates = _frame()

    score = cox_fit(time, event, covariates)["score_test"]

    if score["chi2"] is None:
        assert score["note"]
    else:
        assert score["chi2"] >= 0
        assert 0.0 <= score["p_value"] <= 1.0


def test_schoenfeld_ph_check() -> None:
    """B14: 输出各协变量 Schoenfeld 残差与时间的 Spearman 相关。"""
    time, event, covariates = _frame()

    checks = cox_fit(time, event, covariates)["ph_check"]

    assert len(checks) == covariates.shape[1]
    for item in checks:
        assert -1.0 <= item["rho"] <= 1.0
        assert 0.0 <= item["p_value"] <= 1.0
        assert isinstance(item["violated"], bool)


def test_rmst_trapezoid_and_tau() -> None:
    """B15: RMST 用阶梯曲线积分，τ 决定截断位置。"""
    time = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
    event = np.array([1, 1, 1, 1, 1])

    result = rmst(time, event, tau=8.0)

    # S: 0.8(2), 0.6(4), 0.4(6), 0.2(8), 0(10)
    # 面积 = 1×2 + 0.8×2 + 0.6×2 + 0.4×2 = 5.6
    assert result["tau"] == 8.0
    assert result["rmst"] == pytest.approx(5.6, rel=1e-9)
    assert result["se"] >= 0
    assert result["ci_low"] <= result["rmst"] <= result["ci_high"]


def test_rmst_flags_tau_beyond_followup() -> None:
    """B15: τ 超过最大随访时间时标记截断。"""
    time = np.array([1.0, 2.0, 3.0])
    event = np.array([1, 1, 1])

    result = rmst(time, event, tau=10.0)

    assert result["truncated"] is True
    assert result["rmst"] == pytest.approx(1.0 + 2 / 3 + 1 / 3, rel=1e-9)

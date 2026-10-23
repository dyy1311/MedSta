"""023 教材例题回归：描述指标、分布判定与医学参考值范围。

数值基准来自《医学统计学》第 8 版（李康、贺佳）第二、三、十一章例题。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp_stats

from medsta.agents.discussion import PlanStep
from medsta.stats import methods
from medsta.stats.descriptive import classify_distribution, descriptive_stats


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 步骤",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="教材口径校验",
    )


# 例 2-6：甲乙两名高血压患者连续 5 天收缩压（mmHg）
EXAMPLE_2_6_A = np.array([162.0, 145.0, 178.0, 142.0, 186.0])
EXAMPLE_2_6_B = np.array([164.0, 160.0, 163.0, 159.0, 166.0])

# 例 2-2：24 名健康志愿者中和抗体滴度倒数
EXAMPLE_2_2 = np.array(
    [64, 128, 128, 128, 512, 64, 128, 256, 128, 256, 256, 512,
     512, 512, 256, 128, 128, 512, 256, 256, 64, 512, 256, 256],
    dtype=float,
)


def test_distribution_classification_four_states() -> None:
    """B4: 四态判定——样本不足 / 正态 / 对数正态 / 偏态。"""
    quantiles = sp_stats.norm.ppf(np.linspace(0.02, 0.98, 60))
    assert classify_distribution(quantiles).kind == "normal"
    assert classify_distribution(quantiles).recommended == "x̄±s"

    log_normal = np.exp(sp_stats.norm.ppf(np.linspace(0.02, 0.98, 60)) * 0.5 + 1.0)
    decision = classify_distribution(log_normal)
    assert decision.kind == "log_normal"
    assert decision.recommended == "G"

    bimodal = np.concatenate([np.linspace(1.0, 2.0, 30), np.linspace(50.0, 60.0, 30)])
    assert classify_distribution(bimodal).kind == "skewed"
    assert classify_distribution(bimodal).recommended == "M(P25~P75)"

    assert classify_distribution(np.array([1.0, 2.0])).kind == "insufficient"


def test_descriptive_matches_example_2_6() -> None:
    """B5: 例 2-6 甲患者标准差 19.49、乙患者 2.88（教材公式 2-12）。"""
    df = pd.DataFrame(
        {
            "group": ["甲"] * 5 + ["乙"] * 5,
            "sbp": list(EXAMPLE_2_6_A) + list(EXAMPLE_2_6_B),
        }
    )
    step = _step("descriptive_stats", ["sbp"], group_by="group")

    result = descriptive_stats(df, step, step.params)

    entry = result["columns"]["sbp"]
    assert entry["groups"]["甲"]["mean"] == pytest.approx(162.6, abs=0.01)
    assert entry["groups"]["甲"]["sd"] == pytest.approx(19.49, abs=0.01)
    assert entry["groups"]["乙"]["mean"] == pytest.approx(162.4, abs=0.01)
    assert entry["groups"]["乙"]["sd"] == pytest.approx(2.88, abs=0.01)
    assert entry["groups"]["甲"]["range"] == pytest.approx(44.0)
    assert entry["groups"]["甲"]["recommended"] in ("x̄±s", "M(P25~P75)")


def test_descriptive_cv_matches_formula() -> None:
    """B5: CV = S/x̄×100%（教材公式 2-15；例 2-8 以 10.7/77.5 得 13.81%）。"""
    from medsta.stats.descriptive import _describe_values

    data = np.array([70.0, 74.5, 80.5, 85.0])
    entry = _describe_values(data)
    expected_sd = float(np.std(data, ddof=1))

    assert entry["mean"] == pytest.approx(77.5, abs=0.01)
    assert entry["sd"] == pytest.approx(expected_sd, abs=1e-3)
    assert entry["cv"] == pytest.approx(expected_sd / data.mean() * 100, abs=1e-3)
    # 与教材例 2-8 同一口径：10.7/77.5×100 = 13.81%
    assert 10.7 / 77.5 * 100 == pytest.approx(13.81, abs=0.01)


def test_geometric_mean_matches_example_2_2() -> None:
    """B6: 例 2-2 抗体几何平均滴度 ≈ 209，且 G ≤ x̄。"""
    df = pd.DataFrame({"titre": EXAMPLE_2_2})
    step = _step("descriptive_stats", ["titre"])

    result = descriptive_stats(df, step, step.params)

    entry = result["columns"]["titre"]
    assert entry["geometric_mean"] == pytest.approx(209, abs=1)
    assert entry["geometric_mean"] <= entry["mean"]
    assert entry["distribution"] == "log_normal"
    assert entry["recommended"] == "G"


def test_geometric_mean_requires_positive_values() -> None:
    """B6: 含 0 或负值时不能计算几何均数。"""
    from medsta.stats.descriptive import _describe_values

    entry = _describe_values(np.array([0.0, 1.0, 2.0, 3.0]))

    assert entry["geometric_mean"] is None
    assert "0" in entry["reason"] or "正" in entry["reason"]


def test_descriptive_outputs_full_metrics() -> None:
    """B5: 每次描述都给出 n/均值/标准差/CV/中位数/四分位/IQR/极差/众数/偏度。"""
    df = pd.DataFrame({"value": [1.0, 2.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]})
    step = _step("descriptive_stats", ["value"])

    entry = descriptive_stats(df, step, step.params)["columns"]["value"]

    for key in (
        "n", "mean", "sd", "cv", "median", "q25", "q75", "iqr",
        "min", "max", "range", "mode", "skewness",
        "distribution", "recommended", "reason",
    ):
        assert key in entry, key
    assert entry["iqr"] == pytest.approx(entry["q75"] - entry["q25"])
    assert entry["range"] == pytest.approx(entry["max"] - entry["min"])
    assert entry["mode"] == 2.0


def test_reference_range_accepts_numeric_percentage(tmp_path) -> None:
    """B9: 模型把百分数写成数字 95 时不应被 choice 校验误拒。"""
    from medsta.stats.registry import execute_step, validate_step

    df = pd.DataFrame({"crp": np.linspace(1.0, 20.0, 40)})
    step = _step("reference_range", ["crp"], percentage=95, sides="two", method="normal")

    issues = validate_step(step, df)
    assert [issue for issue in issues if issue.code == "INVALID_PARAM"] == []

    result, _ = execute_step(df, step, tmp_path, 0)
    assert result["percentage"] == 95
    assert result["method"] == "normal"


def test_large_sample_uses_skewness_primarily() -> None:
    """B4（023 修正）: n≥500 时 Shapiro 对微小偏离过度敏感，改以偏度为主判据。"""
    rng = np.random.default_rng(24)
    values = rng.normal(40.0, 10.0, 800)
    values[0] = 95.0

    decision = classify_distribution(values)

    assert decision.shapiro_p < 0.05
    assert decision.kind == "normal"
    assert decision.recommended == "x̄±s"


def test_dominant_value_is_skewed() -> None:
    """B4（023 修正）: 单一取值占比过半（评分两端堆积）判偏态。"""
    values = np.concatenate([np.zeros(600), np.full(250, 8.0), np.linspace(1.0, 7.0, 150)])

    decision = classify_distribution(values)

    assert decision.kind == "skewed"
    assert decision.recommended == "M(P25~P75)"


def test_method_notes_cover_registry_and_execution() -> None:
    """B15: 每个注册工具都有教材口径说明，执行结果自动携带。"""
    from medsta.stats import registry
    from medsta.stats.notes import METHOD_NOTES

    names = {spec.name for spec in registry.all_tools()}
    assert names <= set(METHOD_NOTES), sorted(names - set(METHOD_NOTES))

    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    step = _step("describe", ["value"])

    result, artifact = registry.execute_step(df, step, "/tmp", 0)

    assert artifact is None
    assert result["method_note"] == METHOD_NOTES["describe"]
    assert "§2" in result["method_note"]


def test_correlation_matches_example_11_2() -> None:
    """B12: 例 11-2 身高与前臂长 r≈0.801，并给出 r² 与因果提示。"""
    df = pd.DataFrame(
        {
            "height": [170, 173, 160, 155, 173, 188, 178, 183, 180, 165, 166],
            "forearm": [47, 42, 44, 41, 47, 50, 47, 46, 49, 43, 44],
        }
    )
    step = _step("correlation", ["height", "forearm"], method="pearson")

    result = methods.correlation(df, step, step.params)

    pair = result["pairs"]["height_forearm"]
    assert pair["r"] == pytest.approx(0.801, abs=0.001)
    assert pair["r_squared"] == pytest.approx(0.801**2, abs=0.01)
    # 0.801 恰在教材分档边界，正文称「较高」而规则为「很高」，此处不锁定单一标签
    assert pair["strength"] in ("较高", "很高")
    assert "因果" in result["causality_note"]


def test_reference_range_normal_matches_example_3_3() -> None:
    """B8: 例 3-3 双侧 95%：4.78±1.96×0.38 → (4.04, 5.52)。"""
    from medsta.stats.descriptive import _normal_bounds

    lower, upper, z_value = _normal_bounds(4.78, 0.38, percentage=95, sides="two")

    assert z_value == pytest.approx(1.959964, rel=1e-5)
    assert round(lower, 2) == 4.04
    assert round(upper, 2) == 5.52


def test_reference_range_percentile_sides() -> None:
    """B9: 百分位数法 90/95/99 与双侧/单侧。"""
    from medsta.stats.descriptive import compute_reference_range

    values = np.arange(1, 201, dtype=float)

    # 1..200 的线性插值分位数：P2.5=5.975、P97.5=195.025、P95=190.05、P10=20.9
    two_sided = compute_reference_range(values, percentage=95, sides="two", method="percentile")
    assert two_sided["lower"] == pytest.approx(5.975, abs=1e-6)
    assert two_sided["upper"] == pytest.approx(195.025, abs=1e-6)
    assert two_sided["percentiles"] == [2.5, 97.5]

    upper_only = compute_reference_range(values, percentage=95, sides="one_upper", method="percentile")
    assert upper_only["lower"] is None
    assert upper_only["upper"] == pytest.approx(190.05, abs=1e-6)

    lower_90 = compute_reference_range(values, percentage=90, sides="one_lower", method="percentile")
    assert lower_90["lower"] == pytest.approx(20.9, abs=1e-6)
    assert lower_90["upper"] is None

    wide = compute_reference_range(values, percentage=99, sides="two", method="percentile")
    assert wide["percentiles"] == [0.5, 99.5]


def test_reference_range_log_normal_restores_scale() -> None:
    """B10: 对数正态法先取对数、再用 z 计算、最后取反对数还原。"""
    from medsta.stats.descriptive import compute_reference_range

    values = np.exp(np.linspace(np.log(4.0), np.log(52.0), 120))
    result = compute_reference_range(values, percentage=95, sides="one_upper", method="log_normal")

    log_values = np.log(values)
    expected_upper = np.exp(log_values.mean() + sp_stats.norm.ppf(0.95) * log_values.std(ddof=1))

    assert result["method"] == "log_normal"
    assert result["lower"] is None
    assert result["upper"] == pytest.approx(expected_upper, rel=1e-6)


def test_reference_range_small_sample_warnings() -> None:
    """B11: 样本量不足时给出稳定性警示。"""
    from medsta.stats.descriptive import compute_reference_range

    small = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    normal_small = compute_reference_range(small, method="normal")
    assert any("样本" in item for item in normal_small["warnings"])

    modest = np.arange(1, 51, dtype=float)
    percentile_modest = compute_reference_range(modest, method="percentile")
    assert any("100" in item for item in percentile_modest["warnings"])


def test_reference_range_tool_reports_table() -> None:
    """B8-B10: 工具 handler 输出表格与所用方法。"""
    from medsta.stats.descriptive import reference_range

    df = pd.DataFrame({"crp": np.exp(np.linspace(np.log(1.0), np.log(20.0), 150))})
    step = _step("reference_range", ["crp"], percentage=95, sides="one_upper", method="auto")

    result = reference_range(df, step, step.params)

    assert result["column"] == "crp"
    assert result["method"] in ("normal", "log_normal", "percentile")
    assert result["table"]["rows"][0]["sides"] == "one_upper"
    assert result["method_note"] == "§3 表3-1：正态法双侧 x̄±1.96s、单侧 x̄±1.64s（95%）；百分位数法双侧 P2.5~P97.5。单双侧须由专业知识确定；百分位数法要求样本量较大，n 偏小时两端界值不稳定。"

"""019 B8–B11：12 类统计方法的数值口径与策略链。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp_stats

from medsta.agents.discussion import PlanStep
from medsta.stats import methods
from medsta.stats.registry import validate_step


def _step(method: str, targets: list[str], chart: str = "none", **params) -> PlanStep:
    return PlanStep(
        title=f"{method} 步骤",
        method=method,
        target_columns=targets,
        chart_type=chart,
        params=params,
        rationale="测试用确定性依据",
    )


def _two_group_normal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A"] * 10 + ["B"] * 10,
            "value": [
                9.80, 10.20, 10.00, 9.90, 10.10, 10.30, 9.70, 10.05, 9.95, 10.15,
                11.80, 12.20, 12.00, 11.90, 12.10, 12.30, 11.70, 12.05, 11.95, 12.15,
            ],
        }
    )


def _three_group_normal() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A"] * 8 + ["B"] * 8 + ["C"] * 8,
            "value": [
                9.8, 10.2, 10.0, 9.9, 10.1, 10.3, 9.7, 10.05,
                11.8, 12.2, 12.0, 11.9, 12.1, 12.3, 11.7, 12.05,
                13.8, 14.2, 14.0, 13.9, 14.1, 14.3, 13.7, 14.05,
            ],
        }
    )


def test_describe_reports_overall_and_group_seven_key_stats() -> None:
    """B8: describe 输出整体+分组七列口径（count/mean/median/q25/q75/min/max）。"""
    df = pd.DataFrame({"group": ["A", "A", "B"], "value": [1.0, 3.0, 10.0]})
    step = _step("describe", ["value"], group_by="group")

    result = methods.describe(df, step, step.params)

    overall = result["stats"]["value"]["overall"]
    assert overall["count"] == 3
    assert overall["mean"] == pytest.approx(14 / 3, abs=1e-4)
    assert result["stats"]["value"]["groups"]["A"]["mean"] == 2.0
    assert result["stats"]["value"]["groups"]["B"]["count"] == 1
    assert result["table"]["columns"] == [
        "column", "count", "mean", "median", "q25", "q75", "min", "max",
    ]


def test_describe_categorical_outputs_frequency_table() -> None:
    """B8: 类别列输出频数/占比表，且不混入数值统计。"""
    df = pd.DataFrame({"city": ["a", "a", "b", "c", "a"]})
    step = _step("describe", ["city"])

    result = methods.describe(df, step, step.params)

    rows = {row["value"]: row for row in result["table"]["rows"]}
    assert rows["a"]["count"] == 3
    assert rows["a"]["ratio"] == 0.6
    assert result["stats"]["city"]["distinct"] == 3


def test_normality_test_threshold_is_consistent() -> None:
    """B8: is_normal 与 p>α 一致；n<3 时返回不可判定而非崩溃。"""
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"value": rng.normal(size=40)})
    step = _step("normality_test", ["value"], alpha=0.01)

    result = methods.normality_test(df, step, step.params)["columns"]["value"]
    assert result["n"] == 40
    assert result["is_normal"] is (result["p_value"] > 0.01)

    tiny = methods.normality_test(
        pd.DataFrame({"value": [1.0, 2.0]}), _step("normality_test", ["value"]), {}
    )["columns"]["value"]
    assert tiny["p_value"] is None and tiny["is_normal"] is False


def test_levene_distinguishes_equal_and_unequal_variance() -> None:
    """B8: 方差齐/不齐的判定与 p>α 一致。"""
    equal = _two_group_normal()
    step = _step("levene_test", ["value"], group_column="group")
    homogeneous = methods.levene_test(equal, step, step.params)
    assert homogeneous["homogeneous"] is (homogeneous["p_value"] > 0.05)

    spread = pd.DataFrame(
        {
            "group": ["A"] * 8 + ["B"] * 8,
            "value": [10, 10.1, 9.9, 10.2, 9.8, 10.05, 9.95, 10.15,
                      10, 30, 5, 40, 15, 45, 0, 50],
        }
    )
    unequal = methods.levene_test(spread, step, step.params)
    assert unequal["homogeneous"] is False
    assert "Welch" in unequal["note"]


def test_aggregate_table_supports_mean_and_count() -> None:
    """B8: 分组聚合表按 agg 计算，并保留每组 n。"""
    df = pd.DataFrame({"group": ["A", "A", "B", "B", "B"], "value": [1.0, 2.0, 3.0, 4.0, 5.0]})

    mean_result = methods.aggregate_table(
        df, _step("aggregate_table", ["value"], group_column="group", agg="mean"),
        {"group_column": "group", "agg": "mean"},
    )
    assert [row["value"] for row in mean_result["table"]["rows"]] == [1.5, 4.0]
    assert [row["n"] for row in mean_result["table"]["rows"]] == [2, 3]

    count_result = methods.aggregate_table(
        df, _step("aggregate_table", ["value"], group_column="group", agg="count"),
        {"group_column": "group", "agg": "count"},
    )
    assert [row["value"] for row in count_result["table"]["rows"]] == [2.0, 3.0]


def test_group_compare_normal_equal_variance_uses_t() -> None:
    """B9: 正态+方差齐 → t；输出均值差、CI、Cohen's d 与策略链。"""
    df = _two_group_normal()
    step = _step("group_compare", ["value"], group_column="group")

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "t"
    assert result["p_value"] < 0.001
    assert result["mean_diff"] == pytest.approx(10.015 - 12.015, abs=1e-6)
    assert result["ci95"][0] < result["mean_diff"] < result["ci95"][1]
    assert result["cohens_d"] < 0
    assert result["strategy"]["final_method"] == "t"
    assert any("正态性" in item for item in result["strategy"]["steps"])
    assert any("F 检验" in item for item in result["strategy"]["steps"])
    assert "次优" in result["strategy"]["alternative"]
    assert result["stars"] in {"***", "**", "*"}


def test_group_compare_non_normal_degrades_to_mannwhitney() -> None:
    """B9: 明显非正态 → Mann-Whitney（策略链记录降级依据）。"""
    df = pd.DataFrame(
        {
            "group": ["A"] * 10 + ["B"] * 10,
            "value": [1, 1, 1, 1, 1, 1, 1, 1, 1, 100, 2, 2, 2, 2, 2, 2, 2, 2, 2, 101],
        }
    )
    step = _step("group_compare", ["value"], group_column="group")

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "mannwhitney"
    assert "非正态" in " ".join(result["strategy"]["steps"])
    assert result["strategy"]["alternative"].startswith("次优：t")


def test_group_compare_normal_unequal_variance_uses_welch() -> None:
    """B9: 正态但方差不齐 → Welch t。"""
    df = pd.DataFrame(
        {
            "group": ["A"] * 8 + ["B"] * 8,
            "value": [10, 10.1, 9.9, 10.2, 9.8, 10.05, 9.95, 10.15,
                      10, 30, 5, 40, 15, 45, 0, 50],
        }
    )
    step = _step("group_compare", ["value"], group_column="group")

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "welch_t"
    assert "Welch" in " ".join(result["strategy"]["steps"])


def test_group_compare_requires_two_groups() -> None:
    """B9: 单组数据在计划校验阶段被拦截（INSUFFICIENT_DATA）。"""
    df = pd.DataFrame({"group": ["A"] * 5, "value": [1.0, 2.0, 3.0, 4.0, 5.0]})
    step = _step("group_compare", ["value"], group_column="group")

    codes = {issue.code for issue in validate_step(step, df)}

    assert "INSUFFICIENT_DATA" in codes


def test_anova_outputs_overall_pairwise_and_corrected_p() -> None:
    """B9: 三组 ANOVA 输出整体+两两比较，Holm 校正后 p≥原始 p，并带多重性提醒。"""
    df = _three_group_normal()
    step = _step("anova", ["value"], group_column="group", correction="holm")

    result = methods.anova(df, step, step.params)

    assert result["test"] == "anova"
    assert result["p_value"] < 0.001
    assert result["eta_squared"] > 0.8
    rows = result["pairwise"]["rows"]
    assert len(rows) == 3
    for row in rows:
        assert row["adjusted_p"] >= row["p_value"] - 1e-12
        assert row["adjusted_p"] <= 1.0
        assert row["stars"] in {"***", "**", "*", "ns"}
    assert "多重" in result["multiplicity_warning"]
    assert result["pairwise"]["method"] == "holm"
    assert result["table"]["columns"][:3] == ["group_a", "group_b", "mean_diff"]


def test_anova_non_normal_uses_kruskal() -> None:
    """B9: 非正态多组 → Kruskal-Wallis，输出 epsilon_squared。"""
    df = pd.DataFrame(
        {
            "group": ["A"] * 8 + ["B"] * 8 + ["C"] * 8,
            "value": [1, 1, 1, 1, 1, 1, 1, 100, 2, 2, 2, 2, 2, 2, 2, 200,
                      3, 3, 3, 3, 3, 3, 3, 300],
        }
    )
    step = _step("anova", ["value"], group_column="group")

    result = methods.anova(df, step, step.params)

    assert result["test"] == "kruskal"
    assert "epsilon_squared" in result


def test_chi_square_large_sample_uses_chi_square() -> None:
    """B10: 期望频数充足 → 卡方，Cramér's V 与卡方值自洽。"""
    df = pd.DataFrame(
        {
            "sex": ["M"] * 50 + ["F"] * 50,
            "outcome": ["yes"] * 30 + ["no"] * 20 + ["yes"] * 20 + ["no"] * 30,
        }
    )
    step = _step("chi_square", ["sex", "outcome"])

    result = methods.chi_square(df, step, step.params)

    assert result["strategy"]["final_method"] == "chi_square"
    expected_v = math.sqrt(result["chi2"] / (100 * (2 - 1)))
    assert result["cramers_v"] == pytest.approx(expected_v)
    assert 0.0 <= result["p_value"] <= 1.0


def test_chi_square_small_expected_degrades_to_fisher() -> None:
    """B10: 2×2 期望频数不足 → Fisher 精确检验。"""
    # 列联表：[[8, 2], [1, 4]] → 最小期望频数 2（<5），2×2 应降级 Fisher
    df = pd.DataFrame(
        {
            "exposure": ["yes"] * 10 + ["no"] * 5,
            "outcome": ["case"] * 8 + ["control"] * 2 + ["case"] + ["control"] * 4,
        }
    )
    step = _step("chi_square", ["exposure", "outcome"])

    result = methods.chi_square(df, step, step.params)

    assert result["strategy"]["final_method"] == "fisher_exact"
    assert "odds_ratio" in result
    assert any("Fisher" in item for item in result["strategy"]["steps"])


def test_correlation_perfect_linear_relationship() -> None:
    """B11: 完全线性关系 → Pearson r=1、p≈0，并输出逐对表。"""
    df = pd.DataFrame({"x": range(1, 11), "y": [2 * value + 3 for value in range(1, 11)]})
    step = _step("correlation", ["x", "y"])

    result = methods.correlation(df, step, step.params)

    pair = result["pairs"]["x_y"]
    assert pair["r"] == pytest.approx(1.0)
    assert pair["p_value"] == pytest.approx(0.0, abs=1e-12)
    assert result["matrix"]["x"]["y"] == pytest.approx(1.0)
    assert result["table"]["rows"][0]["pair"] == "x_y"


def test_regression_recovers_known_coefficients() -> None:
    """B11: y=2x+3 → 斜率 2、截距 3、R²=1，CI 覆盖估计值。"""
    df = pd.DataFrame({"x": range(1, 21), "y": [2 * value + 3 for value in range(1, 21)]})
    step = _step("regression", ["y"], target="y", features=["x"])

    result = methods.regression(df, step, step.params)

    assert result["coefficients"]["x"]["estimate"] == pytest.approx(2.0, abs=1e-8)
    assert result["coefficients"]["const"]["estimate"] == pytest.approx(3.0, abs=1e-8)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-10)
    assert result["n"] == 20


def test_logistic_regression_learns_signal() -> None:
    """B11: 有信号的二分类数据 → OR>1、AUC>0.6、准确率>0.5。"""
    rng = np.random.default_rng(11)
    x = rng.normal(size=160)
    probability = 1 / (1 + np.exp(-1.4 * x))
    y = (rng.random(160) < probability).astype(int)
    df = pd.DataFrame({"x": x, "y": y})
    step = _step("logistic_regression", ["y"], target="y", features=["x"])

    result = methods.logistic_regression(df, step, step.params)

    assert result["odds_ratios"]["x"]["odds_ratio"] > 1
    assert result["auc"] > 0.6
    assert result["accuracy"] > 0.5
    assert 0.0 < result["event_rate"] < 1.0


def test_logistic_rejects_perfect_separation() -> None:
    """B4(020): 完全分离时 OR 不可估计，必须报错而不是输出天文数字。"""
    df = pd.DataFrame(
        {
            "x": [-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0],
            "y": [0, 0, 0, 0, 1, 1, 1, 1],
        }
    )
    step = _step("logistic_regression", ["y"], target="y", features=["x"])

    with pytest.raises(ValueError) as excinfo:
        methods.logistic_regression(df, step, step.params)

    message = str(excinfo.value)
    assert "分离" in message
    assert "OR" in message
    assert "Firth" in message or "协变量" in message


def test_logistic_normal_data_has_finite_odds_ratios() -> None:
    """B5(020): 非分离数据的所有 OR/CI 必须是有限值。"""
    rng = np.random.default_rng(21)
    x = rng.normal(size=200)
    probability = 1 / (1 + np.exp(-0.9 * x))
    y = (rng.random(200) < probability).astype(int)
    df = pd.DataFrame({"x": x, "y": y})
    step = _step("logistic_regression", ["y"], target="y", features=["x"])

    result = methods.logistic_regression(df, step, step.params)

    for entry in result["odds_ratios"].values():
        assert math.isfinite(entry["odds_ratio"])
        assert math.isfinite(entry["ci_low"])
        assert math.isfinite(entry["ci_high"])
        assert entry["ci_low"] <= entry["ci_high"]


def test_logistic_regression_rejects_non_binary_outcome() -> None:
    """B11: 非 0/1 结局在实现层也会拒绝（不只靠计划校验）。"""
    df = pd.DataFrame({"x": range(10), "y": range(10)})
    step = _step("logistic_regression", ["y"], target="y", features=["x"])

    with pytest.raises(ValueError, match="0/1"):
        methods.logistic_regression(df, step, step.params)


def test_timeseries_forecast_continues_linear_trend() -> None:
    """B11: 线性序列 → 斜率 1、R²=1、预测值延续趋势。"""
    df = pd.DataFrame({"visit": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]})
    step = _step("timeseries_forecast", ["visit"], forecast_n=3)

    result = methods.timeseries_forecast(df, step, step.params)

    assert result["slope"] == pytest.approx(1.0)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["forecast_values"] == pytest.approx([11.0, 12.0, 13.0])
    # 图表需要预测值回写 step.params
    assert step.params["_forecast_values"] == pytest.approx([11.0, 12.0, 13.0])


def test_correlation_strength_boundaries() -> None:
    """B12: 相关强度分档边界（教材 §11 注意事项 2）。"""
    from medsta.stats.methods import _strength_label

    assert _strength_label(0.0) == "较差"
    assert _strength_label(0.3) == "较差"
    assert _strength_label(0.31) == "中度"
    assert _strength_label(0.6) == "中度"
    assert _strength_label(0.61) == "较高"
    assert _strength_label(0.8) == "较高"
    assert _strength_label(0.81) == "很高"
    assert _strength_label(-0.95) == "很高"


def test_regression_anova_table_identity() -> None:
    """B13: 方差分析表满足 SS总 = SS回归 + SS残差，F = MS回归 / MS残差。"""
    rng = np.random.default_rng(11)
    x = np.linspace(1, 20, 20)
    y = 2.0 * x + 1.0 + rng.normal(0, 0.5, 20)
    df = pd.DataFrame({"x": x, "y": y})
    step = _step("regression", ["y"], target="y", features=["x"])

    result = methods.regression(df, step, step.params)

    table = result["anova_table"]
    assert table["ss_total"] == pytest.approx(
        table["ss_regression"] + table["ss_residual"], rel=1e-9
    )
    assert table["ms_regression"] == pytest.approx(
        table["ss_regression"] / table["df_regression"], rel=1e-9
    )
    assert table["f_value"] == pytest.approx(
        table["ms_regression"] / table["ms_residual"], rel=1e-9
    )
    assert table["df_regression"] == 1
    assert table["df_residual"] == 18


def test_regression_diagnostics_reported() -> None:
    """B14: 回归输出残差正态性、等方差与样本量提示。"""
    rng = np.random.default_rng(13)
    x = np.linspace(1, 8, 8)
    y = 1.5 * x + 2.0 + rng.normal(0, 0.3, 8)
    df = pd.DataFrame({"x": x, "y": y})
    step = _step("regression", ["y"], target="y", features=["x"])

    diagnostics = methods.regression(df, step, step.params)["diagnostics"]

    assert 0.0 <= diagnostics["residual_shapiro_p"] <= 1.0
    assert 0.0 <= diagnostics["breusch_pagan_p"] <= 1.0
    assert diagnostics["n_per_feature"] == pytest.approx(8.0)
    assert "过拟合" in diagnostics["note"]


def test_mean_diff_ci_uses_t_critical_value() -> None:
    """B1: 均值差 95%CI 用 t 临界值；方差不齐时用 Welch–Satterthwaite 自由度。"""
    df = pd.DataFrame(
        {
            "group": ["A"] * 6 + ["B"] * 6,
            "value": [10, 11, 13, 12, 15, 14, 20, 26, 22, 30, 24, 28],
        }
    )
    step = _step("group_compare", ["value"], group_column="group", test="welch_t")

    result = methods.group_compare(df, step, step.params)

    a = np.array([10, 11, 13, 12, 15, 14], dtype=float)
    b = np.array([20, 26, 22, 30, 24, 28], dtype=float)
    diff = a.mean() - b.mean()
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = math.sqrt(va + vb)
    df_welch = (va + vb) ** 2 / (va**2 / (len(a) - 1) + vb**2 / (len(b) - 1))
    t_critical = sp_stats.t.ppf(0.975, df_welch)

    assert result["ci_method"] == "t"
    assert result["ci_target"] == "mean_diff"
    assert result["df"] == pytest.approx(df_welch, rel=1e-9)
    assert result["t_critical"] == pytest.approx(t_critical, rel=1e-9)
    assert result["ci95"][0] == pytest.approx(diff - t_critical * se, rel=1e-9)
    assert result["ci95"][1] == pytest.approx(diff + t_critical * se, rel=1e-9)
    # 小样本下 t 临界值必然大于正态近似的 1.96
    assert result["t_critical"] > 1.96


def test_paired_uses_difference_normality() -> None:
    """B2: 配对设计对差值做正态性检验；原始值偏态不影响配对 t 的选择。"""
    before = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 100.0])
    diff = np.array([-0.5, -0.3, -0.1, 0.1, 0.3, 0.5, -0.2, 0.2, 0.0, 0.4])
    after = before + diff
    df = pd.DataFrame(
        {
            "group": ["before"] * 10 + ["after"] * 10,
            "value": list(before) + list(after),
        }
    )
    step = _step("group_compare", ["value"], group_column="group", paired=True)

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "t"
    assert any("差值" in item for item in result["strategy"]["steps"])
    # 配对区间基于差值标准误，自由度 n-1
    assert result["df"] == pytest.approx(9.0)
    assert result["t_critical"] == pytest.approx(sp_stats.t.ppf(0.975, 9), rel=1e-9)


def test_paired_non_normal_difference_uses_wilcoxon() -> None:
    """B2: 差值明显非正态时降级为 Wilcoxon 符号秩，而不是 Mann-Whitney U。"""
    before = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    diff = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 50.0])
    df = pd.DataFrame(
        {
            "group": ["before"] * 10 + ["after"] * 10,
            "value": list(before) + list(before + diff),
        }
    )
    step = _step("group_compare", ["value"], group_column="group", paired=True)

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "wilcoxon"
    assert result["p_value"] < 0.05


def test_mannwhitney_reports_median_diff_bootstrap() -> None:
    """B3: 非参数路径给中位数差与 bootstrap 区间，不冒充均值差 CI。"""
    df = pd.DataFrame(
        {
            "group": ["A"] * 10 + ["B"] * 10,
            "value": [1, 1, 2, 2, 2, 3, 3, 4, 5, 40, 8, 9, 9, 10, 10, 11, 12, 12, 13, 60],
        }
    )
    step = _step("group_compare", ["value"], group_column="group", test="mannwhitney")

    result = methods.group_compare(df, step, step.params)

    assert result["test"] == "mannwhitney"
    assert result["ci_method"] == "bootstrap"
    assert result["ci_target"] == "median_diff"
    assert result["median_diff"] == pytest.approx(np.median(df["value"][:10]) - np.median(df["value"][10:]))
    assert "t_critical" not in result
    assert result["ci95"][0] < result["median_diff"] < result["ci95"][1]

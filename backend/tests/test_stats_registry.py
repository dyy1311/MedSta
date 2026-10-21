"""009 统计工具库：参数契约、10 类方法与图表测试。"""
import warnings

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.registry import (
    execute_step,
    tool_catalog,
    validate_step,
)


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "age": [25, 31, 42, 38, 51, 47, 29, 60, 33, 45, 52, 27],
            "sex": ["F", "M", "F", "M", "F", "M", "F", "M", "F", "M", "F", "M"],
            "response": [0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0],
            "score": [3.1, 4.2, 3.8, 5.0, 4.4, 3.9, 2.8, 4.9, 3.3, 4.1, 5.2, 3.6],
            "noise": rng.normal(size=12).round(3),
        }
    )


def _step(method: str, **kwargs) -> PlanStep:
    payload = {"title": f"{method} step", "method": method, "target_columns": ["age"], "rationale": "测试依据",
               "chart_type": "none", "params": {}}
    payload.update(kwargs)
    return PlanStep(**payload)


def test_tool_catalog_lists_ten_methods() -> None:
    """B1: 目录含 10 个方法，每项有参数与图表声明"""
    catalog = tool_catalog()
    names = {tool["name"] for tool in catalog}
    assert {
        "describe", "missing_report", "normality_test", "group_compare", "anova",
        "chi_square", "correlation", "regression", "logistic_regression",
        "timeseries_forecast",
    } <= names
    for tool in catalog:
        assert tool["title"] and tool["category"]
        assert isinstance(tool["charts"], list) and isinstance(tool["params"], list)


def test_missing_required_param_reports_structured_issue() -> None:
    """B2: group_compare 缺 group_column 返回 MISSING_PARAM 而非 KeyError"""
    step = _step("group_compare", target_columns=["age"], params={})
    issues = validate_step(step, _df())
    codes = {issue.code for issue in issues}
    assert "MISSING_PARAM" in codes
    issue = next(i for i in issues if i.code == "MISSING_PARAM")
    assert "group_column" in issue.message
    assert issue.hint


def test_unknown_column_and_unknown_tool() -> None:
    """B3: 列不存在 → COLUMN_NOT_FOUND；方法不存在 → TOOL_NOT_FOUND"""
    column_issue = validate_step(
        _step("describe", target_columns=["not_a_column"]), _df()
    )
    assert {i.code for i in column_issue} == {"COLUMN_NOT_FOUND"}
    from types import SimpleNamespace

    bogus = SimpleNamespace(
        title="magic step", method="magic", target_columns=["age"],
        chart_type="none", params={},
    )
    tool_issue = validate_step(bogus, _df())
    assert {i.code for i in tool_issue} == {"TOOL_NOT_FOUND"}


def test_invalid_choice_param() -> None:
    """B4: 非法枚举取值 → INVALID_PARAM"""
    step = _step(
        "group_compare",
        target_columns=["age"],
        params={"group_column": "sex", "test": "not_a_test"},
    )
    issues = validate_step(step, _df())
    assert "INVALID_PARAM" in {i.code for i in issues}


def test_describe_with_grouping(tmp_path) -> None:
    """B5: describe 支持分组，输出 n/mean/sd/median"""
    step = _step(
        "describe",
        target_columns=["age"],
        params={"group_by": "sex"},
        chart_type="boxplot",
    )
    assert validate_step(step, _df()) == []
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    stats = result["stats"]["age"]
    assert stats["overall"]["n"] == 12
    assert set(stats["groups"]) == {"F", "M"}
    assert artifact and artifact.endswith(".png")


def test_group_compare_outputs_effect_size(tmp_path) -> None:
    """B6: group_compare 输出 test/statistic/p/cohens_d 并生成图表"""
    step = _step(
        "group_compare",
        target_columns=["age"],
        params={"group_column": "sex", "test": "t"},
        chart_type="violin",
    )
    result, artifact = execute_step(_df(), step, tmp_path, 1)
    assert result["test"] == "t"
    assert 0.0 <= result["p_value"] <= 1.0
    assert "cohens_d" in result
    assert artifact and "violin" in artifact


def test_anova_requires_two_groups(tmp_path) -> None:
    """B7: anova 输出 eta_squared；组数不足返回 INSUFFICIENT_DATA"""
    step = _step(
        "anova", target_columns=["age"], params={"group_column": "sex"}
    )
    result, _ = execute_step(_df(), step, tmp_path, 0)
    assert "eta_squared" in result and "p_value" in result

    single = _df().assign(sex="F")
    issues = validate_step(step, single)
    assert "INSUFFICIENT_DATA" in {i.code for i in issues}


def test_chi_square_two_by_two_odds_ratio(tmp_path) -> None:
    """B8: 2×2 卡方输出 OR 与 Cramér's V"""
    step = _step(
        "chi_square",
        target_columns=["sex"],
        params={"row_column": "sex", "col_column": "response"},
    )
    result, _ = execute_step(_df(), step, tmp_path, 0)
    assert "odds_ratio" in result
    assert 0.0 <= result["cramers_v"] <= 1.0


def test_logistic_regression_outputs_odds_ratios(tmp_path) -> None:
    """B9: logistic 回归输出 OR 与 accuracy（非分离数据）"""
    rng = np.random.default_rng(23)
    score = rng.normal(size=120)
    response = (rng.random(120) < 1 / (1 + np.exp(-score))).astype(int)
    df = pd.DataFrame({"score": score, "response": response})
    step = _step(
        "logistic_regression",
        target_columns=["response"],
        params={"target": "response", "features": ["score"]},
        chart_type="bar",
    )
    result, artifact = execute_step(df, step, tmp_path, 0)
    assert "odds_ratios" in result
    assert 0.0 <= result["accuracy"] <= 1.0
    assert np.isfinite(result["odds_ratios"]["score"]["odds_ratio"])
    assert artifact


def test_missing_report(tmp_path) -> None:
    """B10: missing_report 输出逐列缺失数与比例"""
    df = _df()
    df.loc[0, "age"] = np.nan
    df.loc[1, "score"] = np.nan
    step = _step("missing_report", target_columns=["age", "score"])
    result, artifact = execute_step(df, step, tmp_path, 0)
    assert result["columns"]["age"]["missing"] == 1
    assert result["columns"]["age"]["missing_pct"] == 8.33
    assert artifact is None


def test_normality_test(tmp_path) -> None:
    """B11: normality_test 输出 W/p/is_normal"""
    step = _step(
        "normality_test", target_columns=["age"], chart_type="qq_plot"
    )
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    assert 0.0 <= result["columns"]["age"]["p_value"] <= 1.0
    assert isinstance(result["columns"]["age"]["is_normal"], bool)
    assert artifact


def test_correlation_spearman_with_p_values(tmp_path) -> None:
    """B12: correlation 支持 spearman 并输出 p 值"""
    step = _step(
        "correlation",
        target_columns=["age", "score"],
        params={"method": "spearman"},
        chart_type="heatmap",
    )
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    pair = result["pairs"]["age_score"]
    assert -1.0 <= pair["r"] <= 1.0
    assert 0.0 <= pair["p_value"] <= 1.0
    assert artifact


def test_regression_coefficient_confidence_interval(tmp_path) -> None:
    """B13: regression 输出系数 95%CI 与 p 值"""
    step = _step(
        "regression",
        target_columns=["score"],
        params={"target": "score", "features": ["age", "noise"]},
        chart_type="residual_plot",
    )
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    assert "r_squared" in result
    coef = result["coefficients"]["age"]
    assert coef["ci_low"] <= coef["estimate"] <= coef["ci_high"]
    assert 0.0 <= coef["p_value"] <= 1.0
    assert artifact


def test_timeseries_forecast_length(tmp_path) -> None:
    """B14: forecast_values 长度等于 forecast_n"""
    step = _step(
        "timeseries_forecast",
        target_columns=["score"],
        params={"forecast_n": 3},
        chart_type="line",
    )
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    assert len(result["forecast_values"]) == 3
    assert artifact


def test_chart_no_missing_glyph_warning(tmp_path) -> None:
    """B15: 中文标题图表不产生缺字警告"""
    step = _step(
        "describe",
        title="描述性统计：年龄分布",
        target_columns=["age"],
        chart_type="histogram",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        execute_step(_df(), step, tmp_path, 0)
    glyph = [w for w in caught if "missing from font" in str(w.message)]
    assert glyph == []

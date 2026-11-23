"""016 类型驱动方法映射：accepts 校验、ordinal 降级、index 拒绝、默认图。"""
import pandas as pd

from medsta.agents.discussion import PlanStep
from medsta.data.profiler import profile_dataframe
from medsta.stats.plotting import default_chart_for
from medsta.stats.registry import validate_step


def _df() -> pd.DataFrame:
    return pd.DataFrame({
        "age": [25.5, 31.2, 42.8, 38.1, 51.0, 47.3],
        "grade": [1, 2, 3, 2, 1, 3],
        "sex": ["F", "M", "F", "M", "F", "M"],
        "idx": [1, 2, 3, 4, 5, 6],
    })


def _step(method: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{method} step", method=method, target_columns=targets,
        chart_type="none", params=params, rationale="测试依据",
    )


def test_categorical_target_rejected_for_parametric() -> None:
    """B1: group_compare 目标为类别列 → COLUMN_TYPE_MISMATCH 并建议卡方"""
    issues = validate_step(_step("group_compare", ["sex"], group_column="idx"), _df())
    codes = {issue.code for issue in issues}
    assert "COLUMN_TYPE_MISMATCH" in codes
    hint = next(i for i in issues if i.code == "COLUMN_TYPE_MISMATCH").hint
    assert "chi_square" in hint


def test_ordinal_target_soft_hint() -> None:
    """B2: ordinal 目标列用于参数检验 → ORDINAL_HINT 软提示（非阻断）"""
    step = _step("group_compare", ["grade"], group_column="sex", test="t")
    codes = {issue.code for issue in validate_step(step, _df())}
    assert "ORDINAL_HINT" in codes
    assert "COLUMN_TYPE_MISMATCH" not in codes


def test_index_column_rejected() -> None:
    """B3: 用户敲定画像中的 index 列参与统计 → COLUMN_TYPE_MISMATCH"""
    profile = profile_dataframe(_df())
    issues = validate_step(_step("describe", ["idx"]), profile)
    assert {i.code for i in issues} == {"COLUMN_TYPE_MISMATCH"}


def test_chi_square_rejects_continuous() -> None:
    """B4: chi_square 连续列 → COLUMN_TYPE_MISMATCH（建议分箱）"""
    issues = validate_step(
        _step("chi_square", ["age"], row_column="age", col_column="sex"), _df()
    )
    codes = {i.code for i in issues}
    assert "COLUMN_TYPE_MISMATCH" in codes
    hint = next(i for i in issues if i.code == "COLUMN_TYPE_MISMATCH").hint
    assert "分箱" in hint or "类别" in hint


def test_default_chart_by_type() -> None:
    """B5: 类型→默认图"""
    assert default_chart_for("continuous") == "histogram"
    assert default_chart_for("categorical") == "bar"
    assert default_chart_for("ordinal") == "bar"
    assert default_chart_for("index") == "line"


def test_categorical_target_hints_group_column_when_supported() -> None:
    """终审修复: 类别列误当目标列时应指向「作为分组变量」这个真实修法。"""
    issues = validate_step(_step("group_compare", ["sex"], group_column="idx"), _df())
    hint = next(i for i in issues if i.code == "COLUMN_TYPE_MISMATCH").hint
    assert "group_column" in hint
    assert "分组变量" in hint
    # 仍然保留「改用卡方」这条替代路径
    assert "chi_square" in hint


def test_categorical_target_without_group_param_keeps_generic_hint() -> None:
    """工具没有分组参数时（one_sample_test）不能瞎指 group_column。"""
    issues = validate_step(_step("one_sample_test", ["sex"], mu0=0), _df())
    hint = next(i for i in issues if i.code == "COLUMN_TYPE_MISMATCH").hint
    assert "group_column" not in hint
    assert "chi_square" in hint


def test_tool_catalog_exposes_group_param() -> None:
    """装配器需要 group_param 才能提供「设为分组列」入口。"""
    from medsta.stats.registry import tool_catalog

    by_name = {tool["name"]: tool for tool in tool_catalog()}
    assert by_name["group_compare"]["group_param"] == "group_column"
    assert by_name["anova"]["group_param"] == "group_column"
    assert not by_name.get("describe", {}).get("group_param")


def test_params_only_target_tools_pass_validation() -> None:
    """用户实测缺陷: logistic/regression/整存分析的目标在 params 里，target_columns 可留空。

    此前统一要求「至少一个目标列」，导致「是否手术的多因素 Logistic 回归」被判 INVALID_PARAM。
    """
    df = _df()
    cases = [
        (
            "logistic_regression",
            {"target": "sex", "features": ["value"]},
        ),
        ("regression", {"target": "value", "features": ["age"]}),
        ("survival_analysis", {"time_col": "age", "event_col": "sex"}),
    ]
    for method, params in cases:
        step = _step(method, [], **params)
        codes = [issue.code for issue in validate_step(step, df)]
        assert "INVALID_PARAM" not in codes, f"{method} 不应因缺目标列被拒：{codes}"


def test_target_columns_still_required_for_value_tools() -> None:
    """仍要求目标列的工具（如 group_compare）不能因为这次放宽而漏检，且 hint 可操作。"""
    issues = validate_step(_step("group_compare", [], group_column="sex"), _df())
    missing = [issue for issue in issues if issue.code == "INVALID_PARAM"]
    assert missing, "缺少目标列必须报错"
    assert "目标列" in missing[0].message

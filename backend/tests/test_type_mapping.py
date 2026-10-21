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

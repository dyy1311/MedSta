"""019 B12：计划级硬校验（宿主在模型输出后、执行前的闸门）。"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.data.profiler import apply_column_type, profile_dataframe
from medsta.errors import ToolValidationError
from medsta.pipeline.executor import PipelineExecutor
from medsta.stats.registry import HARD_ISSUE_CODES, validate_plan, validate_step


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "group": ["A", "A", "A", "B", "B", "B"],
            "value": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            "outcome": [0, 1, 0, 1, 1, 0],
            "site": ["a", "b", "a", "b", "a", "b"],
            "grade": [1, 2, 3, 4, 5, 3],
        }
    )


def _step(method: str, targets: list[str], chart: str = "none", rationale: str = "有依据", **params) -> PlanStep:
    return PlanStep(
        title=f"{method} 步骤",
        method=method,
        target_columns=targets,
        chart_type=chart,
        params=params,
        rationale=rationale,
    )


def test_valid_plan_has_no_hard_issues() -> None:
    """B12: 合法计划无硬错误，执行器直接放行。"""
    plan = AnalysisPlan(
        message="描述并比较",
        steps=[
            _step("describe", ["value"]),
            _step("group_compare", ["value"], group_column="group"),
        ],
    )

    issues = validate_plan(plan, _df())

    assert [issue for issue in issues if issue.code in HARD_ISSUE_CODES] == []


def test_issues_carry_step_index_for_every_step() -> None:
    """B12: 多步计划的错误定位到具体步骤，前端可跳转修正。"""
    plan = AnalysisPlan(
        message="故意出错",
        steps=[
            _step("describe", ["value"]),
            _step("describe", ["not_a_column"]),
            _step("group_compare", ["value"]),
        ],
    )

    issues = validate_plan(plan, _df())
    by_step = {issue.step_index for issue in issues}

    assert 1 in by_step and 2 in by_step
    assert all(issue.step_index is not None for issue in issues)
    assert {issue.code for issue in issues if issue.step_index == 1} == {"COLUMN_NOT_FOUND"}
    assert "MISSING_PARAM" in {issue.code for issue in issues if issue.step_index == 2}


def test_missing_rationale_is_hard_error() -> None:
    """B12: 没有选择依据的方案被拒绝（可解释性硬要求）。"""
    step = _step("describe", ["value"], rationale="   ")

    issues = validate_step(step, _df())

    assert "MISSING_PARAM" in {issue.code for issue in issues}
    assert "rationale" in issues[0].message


def test_ordinal_target_is_soft_hint_not_blocking() -> None:
    """B12: 等级型目标是软提示（自动走非参数），不阻断执行。"""
    df = _df()
    profile = profile_dataframe(df)
    apply_column_type(df, profile, "grade", "ordinal")
    step = _step("group_compare", ["grade"], group_column="group")

    issues = validate_step(step, profile)
    hard = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]

    assert hard == []
    assert [issue.code for issue in issues] == ["ORDINAL_HINT"]
    assert "Mann-Whitney" in issues[0].hint


def test_logistic_non_binary_target_is_hard_error() -> None:
    """B12: 结局不是 0/1 → INVALID_PARAM（不进入执行器）。"""
    df = _df()
    df["outcome"] = [0, 1, 2, 0, 1, 2]
    step = _step("logistic_regression", ["outcome"], target="outcome", features=["value"])

    issues = validate_step(step, df)

    assert "INVALID_PARAM" in {issue.code for issue in issues}
    assert any("0/1" in issue.message for issue in issues)


def test_chi_square_requires_two_categorical_columns() -> None:
    """B12: 卡方只给一个分类列 → 缺 row_column/col_column。"""
    step = _step("chi_square", ["group"])

    issues = validate_step(step, _df())

    codes = {issue.code for issue in issues}
    assert "MISSING_PARAM" in codes
    assert sum(issue.code == "MISSING_PARAM" for issue in issues) == 2


def test_invalid_chart_for_method_is_hard_error() -> None:
    """B12: 方法不支持的图表类型在计划期被拒绝。"""
    step = _step("correlation", ["value", "grade"], chart="boxplot")

    issues = validate_step(step, _df())

    assert "INVALID_PARAM" in {issue.code for issue in issues}
    assert any("不支持图表" in issue.message for issue in issues)


def test_group_compare_rejects_third_group_instead_of_silently_ignoring() -> None:
    """B12: 两组比较遇到 3 组时拒绝，避免静默丢掉第三组（应改用 ANOVA）。"""
    df = _df().copy()
    df.loc[df.index[:2], "group"] = "C"
    step = _step("group_compare", ["value"], group_column="group")

    issues = validate_step(step, df)

    codes = {issue.code for issue in issues}
    assert "INVALID_PARAM" in codes
    issue = next(issue for issue in issues if "3 组" in issue.message)
    assert "anova" in issue.hint.lower()


def test_executor_rejects_plan_before_touching_disk(tmp_path) -> None:
    """B12: 校验失败时执行器不创建 artifact 目录、不产出半成品报告。"""
    plan = AnalysisPlan(
        message="缺参数",
        steps=[_step("group_compare", ["value"])],
    )
    artifact_dir = tmp_path / "artifacts"

    with pytest.raises(ToolValidationError) as excinfo:
        PipelineExecutor().execute(_df(), plan, artifact_dir=artifact_dir)

    assert excinfo.value.issues
    assert not pathlib.Path(artifact_dir).exists()

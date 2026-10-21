"""013 槽位化工具与检验策略链测试。"""
import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.registry import execute_step, tool_catalog, validate_step

R = "测试依据：数值列、两组独立样本"


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n_a, n_b = 30, 8  # 刻意不平衡
    return pd.DataFrame(
        {
            "group": ["A"] * n_a + ["B"] * n_b,
            "value": np.concatenate([rng.normal(10, 2, n_a), rng.normal(13, 2, n_b)]).round(3),
            "value2": rng.normal(5, 1, n_a + n_b).round(3),
            "cat": rng.choice(["x", "y", "z"], n_a + n_b),
        }
    )


def _step(method: str, **kwargs) -> PlanStep:
    payload = {
        "title": method,
        "method": method,
        "target_columns": ["value"],
        "chart_type": "none",
        "params": {},
        "rationale": R,
    }
    payload.update(kwargs)
    return PlanStep(**payload)


def test_catalog_declares_task_slots_applicability() -> None:
    """B1: 目录每项含 task/applicability/slots；槽位缺失报 MISSING_PARAM"""
    catalog = tool_catalog()
    assert all({"task", "applicability", "slots"} <= set(tool) for tool in catalog)
    issues = validate_step(
        _step("group_compare", target_columns=["value"], params={}), _df()
    )
    assert "MISSING_PARAM" in {i.code for i in issues}


def test_levene_test(tmp_path) -> None:
    """B2: levene 输出 statistic/p/homogeneous"""
    step = _step("levene_test", target_columns=["value"], params={"group_column": "group"})
    result, _ = execute_step(_df(), step, tmp_path, 0)
    assert 0.0 <= result["p_value"] <= 1.0
    assert isinstance(result["homogeneous"], bool)


def test_aggregate_table(tmp_path) -> None:
    """B3: aggregate_table 按 group×value×agg 输出表格数据"""
    step = _step(
        "aggregate_table",
        target_columns=["value"],
        params={"group_column": "group", "agg": "mean"},
    )
    result, _ = execute_step(_df(), step, tmp_path, 0)
    table = result["table"]
    assert "group" in table["columns"] and "value" in table["columns"]
    assert len(table["rows"]) == 2


def test_pie_chart(tmp_path) -> None:
    """B4: 饼图按分类计数渲染"""
    step = _step("describe", target_columns=["cat"], chart_type="pie")
    assert validate_step(step, _df()) == []
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    assert artifact and artifact.endswith(".png")


def test_group_compare_strategy_chain(tmp_path) -> None:
    """B5: 策略链输出 steps 判定、final_method 与次优建议；不平衡提示"""
    step = _step(
        "group_compare",
        target_columns=["value"],
        params={"group_column": "group", "test": "auto"},
        chart_type="boxplot",
    )
    result, artifact = execute_step(_df(), step, tmp_path, 0)
    strategy = result["strategy"]
    assert strategy["final_method"] in ("t", "welch_t", "mannwhitney")
    assert strategy["alternative"]
    joined = " ".join(strategy["steps"])
    assert "正态" in joined
    assert "失衡" in joined or "不平衡" in joined
    assert artifact


def test_anova_pairwise_with_holm(tmp_path) -> None:
    """B6: anova ≥3 组输出 overall + pairwise（Holm 校正）+ 多重性提醒"""
    df = _df().assign(group3=["g1"] * 13 + ["g2"] * 13 + ["g3"] * 12)
    step = _step("anova", target_columns=["value"], params={"group_column": "group3"},
                 chart_type="boxplot")
    result, artifact = execute_step(df, step, tmp_path, 0)
    assert "overall" in result and "pairwise" in result
    pairwise = result["pairwise"]
    assert len(pairwise["rows"]) == 3
    assert "adjusted_p" in pairwise["columns"]
    assert "多重" in result["multiplicity_warning"]
    assert artifact


def test_chi_square_expected_frequency_strategy(tmp_path) -> None:
    """B7: 2×2 期望不足自动 Fisher；大样本用卡方；strategy 记录判定"""
    small = pd.DataFrame(
        {"a": ["y", "y", "y", "n", "n"], "b": ["x", "x", "x", "z", "z"]}
    )
    step = PlanStep(
        title="关联检验",
        method="chi_square",
        target_columns=["a", "b"],
        chart_type="none",
        params={},
        rationale=R,
    )
    result, _ = execute_step(small, step, tmp_path, 0)
    assert result["strategy"]["final_method"] == "fisher_exact"
    assert any("期望" in s for s in result["strategy"]["steps"])

    rng = np.random.default_rng(3)
    big = pd.DataFrame(
        {
            "a": rng.choice(["p", "q"], 400),
            "b": rng.choice(["u", "v"], 400),
        }
    )
    result2, _ = execute_step(big, step, tmp_path, 1)
    assert result2["strategy"]["final_method"] == "chi_square"
    assert result2["strategy"]["alternative"]


def test_significance_label(tmp_path) -> None:
    """B8: 星号与 significant 判定；检验结果含 alpha/significant/stars"""
    from medsta.stats.significance import significance_label

    assert significance_label(0.0005, 0.05)["stars"] == "***"
    assert significance_label(0.02, 0.05)["stars"] == "*"
    assert significance_label(0.4, 0.05) == {"significant": False, "stars": "ns"}
    assert significance_label(0.02, 0.01)["significant"] is False

    step = _step(
        "group_compare",
        target_columns=["value"],
        params={"group_column": "group", "test": "t", "alpha": 0.01},
    )
    result, _ = execute_step(_df(), step, tmp_path, 0)
    assert result["alpha"] == 0.01
    assert "significant" in result and "stars" in result


def test_plan_rationale_required() -> None:
    """B9: PlanStep 缺 rationale 被校验拒绝（MISSING_PARAM）"""
    step = PlanStep.model_construct(
        title="缺依据",
        method="describe",
        target_columns=["value"],
        chart_type="none",
        params={},
        rationale="",
    )
    issues = validate_step(step, _df())
    assert "MISSING_PARAM" in {i.code for i in issues}

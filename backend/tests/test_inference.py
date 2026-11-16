"""024 推断统计新方法的边界行为：单样本、区组方差分析、McNemar、SNK/Dunn。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp_stats

from medsta.agents.discussion import PlanStep
from medsta.stats.inference import one_sample_test


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 步骤",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="边界行为校验",
    )


def test_one_sample_falls_back_to_wilcoxon() -> None:
    """B4: 明显非正态 → Wilcoxon 符号秩，策略链记录降级依据。"""
    values = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 60.0]
    df = pd.DataFrame({"value": values})
    step = _step("one_sample_test", ["value"], mu0=1.0)

    result = one_sample_test(df, step, step.params)

    assert result["test"] == "wilcoxon"
    assert any("Wilcoxon" in item for item in result["strategy"]["steps"])


def test_one_sample_can_force_t() -> None:
    """B4: test=t 时即使偏态也按参数检验执行（用户显式指定）。"""
    values = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 2.0, 60.0]
    df = pd.DataFrame({"value": values})
    step = _step("one_sample_test", ["value"], mu0=1.0, test="t")

    result = one_sample_test(df, step, step.params)

    assert result["test"] == "t"
    assert result["p_value"] < 1.0


def test_one_sided_p_value_direction() -> None:
    """B5: 单侧 p 值等于双侧一半，方向与数据一致。"""
    rng = np.random.default_rng(20261023)
    values = rng.normal(12.0, 2.0, 40)
    df = pd.DataFrame({"value": values})

    two = one_sample_test(
        df, _step("one_sample_test", ["value"], mu0=10.0, sides="two"), {"mu0": 10.0, "sides": "two"}
    )
    greater = one_sample_test(
        df, _step("one_sample_test", ["value"], mu0=10.0, sides="greater"),
        {"mu0": 10.0, "sides": "greater"},
    )
    less = one_sample_test(
        df, _step("one_sample_test", ["value"], mu0=10.0, sides="less"),
        {"mu0": 10.0, "sides": "less"},
    )

    assert greater["p_value"] == pytest.approx(two["p_value"] / 2, rel=1e-6)
    assert less["p_value"] == pytest.approx(1 - two["p_value"] / 2, rel=1e-6)
    assert greater["p_value"] < less["p_value"]
    assert 0.0 <= greater["p_value"] <= 1.0


def test_one_sample_rejects_missing_mu0() -> None:
    """B3: mu0 必填，缺失时给出可读错误。"""
    df = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]})
    step = _step("one_sample_test", ["value"])

    with pytest.raises(KeyError):
        one_sample_test(df, step, step.params)


def _example_8_3_frame() -> pd.DataFrame:
    """例 8-3 的三组结构：均值 37.83/35.10/33.62，组内 SS 合计 188.76（MSE=6.9912）。"""
    perturbation = np.linspace(-1.0, 1.0, 10)
    perturbation = perturbation * np.sqrt(62.92 / np.sum(perturbation**2))
    rows = []
    for label, mean in (("A", 37.83), ("B", 35.10), ("C", 33.62)):
        for offset in perturbation:
            rows.append({"group": label, "value": mean + offset})
    return pd.DataFrame(rows)


def test_block_anova_sum_of_squares_identity() -> None:
    """B6: SS总 = SS处理 + SS区组 + SS误差，自由度分解一致。"""
    from medsta.stats.inference import randomized_block_anova

    frame = pd.DataFrame(
        {
            "treatment": ["T1"] * 4 + ["T2"] * 4 + ["T3"] * 4,
            "block": ["B1", "B2", "B3", "B4"] * 3,
            "value": [
                10.0, 12.1, 11.0, 12.9,
                14.2, 16.0, 14.9, 17.0,
                11.8, 14.0, 13.2, 15.0,
            ],
        }
    )
    step = _step("randomized_block_anova", ["value"], group_column="treatment", block_column="block")

    result = randomized_block_anova(frame, step, step.params)

    assert result["ss_total"] == pytest.approx(
        result["ss_treatment"] + result["ss_block"] + result["ss_error"], rel=1e-9
    )
    assert result["df_treatment"] == 2
    assert result["df_block"] == 3
    assert result["df_error"] == 6
    assert result["ms_error"] == pytest.approx(result["ss_error"] / 6, rel=1e-9)
    assert result["f_treatment"] == pytest.approx(
        result["ms_treatment"] / result["ms_error"], rel=1e-9
    )


def test_block_anova_reports_treatment_and_block() -> None:
    """B7: 同时输出处理效应与区组效应的 F/p。"""
    from medsta.stats.inference import randomized_block_anova

    frame = pd.DataFrame(
        {
            "treatment": ["T1"] * 4 + ["T2"] * 4 + ["T3"] * 4,
            "block": ["B1", "B2", "B3", "B4"] * 3,
            "value": [
                10.0, 12.1, 11.0, 12.9,
                14.2, 16.0, 14.9, 17.0,
                11.8, 14.0, 13.2, 15.0,
            ],
        }
    )
    step = _step("randomized_block_anova", ["value"], group_column="treatment", block_column="block")

    result = randomized_block_anova(frame, step, step.params)

    assert 0.0 <= result["p_treatment"] <= 1.0
    assert 0.0 <= result["p_block"] <= 1.0
    assert result["f_treatment"] > 0
    assert result["f_block"] > 0
    assert result["method_note"].startswith("§8")


def test_snk_q_matches_example_8_3() -> None:
    """B8: 例 8-3 q=5.04/3.27/1.77，跨度 3/2/2。"""
    from medsta.stats.significance import snk_q_pvalue

    q_ac, p_ac = snk_q_pvalue(37.83, 33.62, 10, 10, 6.9912, 27, 3)
    q_ab, p_ab = snk_q_pvalue(37.83, 35.10, 10, 10, 6.9912, 27, 2)
    q_bc, p_bc = snk_q_pvalue(35.10, 33.62, 10, 10, 6.9912, 27, 2)

    assert q_ac == pytest.approx(5.04, abs=0.01)
    assert q_ab == pytest.approx(3.27, abs=0.01)
    assert q_bc == pytest.approx(1.77, abs=0.01)
    assert p_ac < 0.05
    assert p_ab < 0.05
    assert p_bc > 0.05


def test_anova_snk_posthoc_uses_q_and_span() -> None:
    """B8: ANOVA 事后默认 SNK，输出 q 值、跨度与逐步判定。"""
    from medsta.stats.methods import anova

    frame = _example_8_3_frame()
    step = _step("anova", ["value"], group_column="group")

    result = anova(frame, step, step.params)
    rows = result["pairwise"]["rows"]
    by_pair = {(row["group_a"], row["group_b"]): row for row in rows}

    assert result["pairwise"]["method"] == "snk"
    assert by_pair[("A", "C")]["span"] == 3
    assert by_pair[("A", "C")]["q_value"] == pytest.approx(5.04, abs=0.02)
    assert by_pair[("B", "C")]["span"] == 2
    assert by_pair[("B", "C")]["significant"] is False
    assert by_pair[("A", "C")]["significant"] is True


def test_snk_step_down_rule_blocks_smaller_spans() -> None:
    """B9: 跨度最大的比较不显著时，更小跨度不再判为显著（原始 p 仍保留）。"""
    from medsta.stats.significance import snk_step_down

    rows = [
        {"group_a": "A", "group_b": "C", "span": 3, "q_value": 1.2, "p_value": 0.42},
        {"group_a": "A", "group_b": "B", "span": 2, "q_value": 2.9, "p_value": 0.04},
        {"group_a": "B", "group_b": "C", "span": 2, "q_value": 2.1, "p_value": 0.12},
    ]

    decided = snk_step_down(rows, alpha=0.05)

    by_span = {(row["group_a"], row["group_b"]): row for row in decided}
    assert by_span[("A", "C")]["significant"] is False
    assert by_span[("A", "B")]["significant"] is False
    assert by_span[("A", "B")]["p_value"] == pytest.approx(0.04)
    assert by_span[("A", "B")]["step_down"] is True


def test_anova_holm_still_available() -> None:
    """B10: correction=holm 时仍按 Holm 校正，输出列保持一致。"""
    from medsta.stats.methods import anova

    frame = _example_8_3_frame()
    step = _step("anova", ["value"], group_column="group", correction="holm")

    result = anova(frame, step, step.params)
    rows = result["pairwise"]["rows"]

    assert result["pairwise"]["method"] == "holm"
    assert all("adjusted_p" in row for row in rows)
    assert all("significant" in row for row in rows)


def test_kruskal_dunn_posthoc() -> None:
    """B11: Kruskal 路径用 Dunn + Bonferroni，说明教材未给公式。"""
    from medsta.stats.methods import anova

    rng = np.random.default_rng(24)
    frame = pd.DataFrame(
        {
            "group": ["A"] * 12 + ["B"] * 12 + ["C"] * 12,
            "value": np.concatenate(
                [rng.lognormal(1.0, 0.8, 12), rng.lognormal(1.6, 0.8, 12), rng.lognormal(2.0, 0.8, 12)]
            ),
        }
    )
    step = _step("anova", ["value"], group_column="group")

    result = anova(frame, step, step.params)

    assert result["test"] == "kruskal"
    assert result["pairwise"]["method"] == "dunn"
    assert all("adjusted_p" in row for row in result["pairwise"]["rows"])
    assert "Dunn" in result["method_note"]


def _fourfold(a: int, b: int, c: int, d: int) -> pd.DataFrame:
    rows = [("A", "X")] * a + [("A", "Y")] * b + [("B", "X")] * c + [("B", "Y")] * d
    return pd.DataFrame(rows, columns=["group", "event"])


def test_fourfold_three_tiers() -> None:
    """B12: n≥40&T≥5 用专用公式；n≥40&1≤T<5 用校正；n<40 或 T<1 用 Fisher。"""
    from medsta.stats.methods import chi_square

    # 档 1：n=200，最小期望频数远大于 5
    big = _fourfold(60, 40, 40, 60)
    big_result = chi_square(big, _step("chi_square", ["group", "event"]), {})
    assert big_result["tier"] == "pearson"
    assert big_result["corrected"] is False

    # 档 2：n=50，最小期望 4.4（1≤T<5）→ 校正公式
    mid = _fourfold(1, 19, 10, 20)
    mid_result = chi_square(mid, _step("chi_square", ["group", "event"]), {})
    assert mid_result["tier"] == "corrected"
    assert mid_result["corrected"] is True

    # 档 3：n=20 < 40 → Fisher
    small = _fourfold(1, 9, 5, 5)
    small_result = chi_square(small, _step("chi_square", ["group", "event"]), {})
    assert small_result["tier"] == "fisher"


def test_fourfold_explicit_correction_still_works() -> None:
    """B12: 显式 correction=no 时不校正，=yes 时校正（布尔旧值需兼容）。"""
    from medsta.stats.methods import chi_square

    frame = _fourfold(60, 40, 40, 60)
    step = _step("chi_square", ["group", "event"])

    forced = chi_square(frame, step, {"correction": "no"})
    legacy = chi_square(frame, step, {"correction": True})

    assert forced["corrected"] is False
    assert legacy["corrected"] is True


def test_mcnemar_corrected_when_b_plus_c_small() -> None:
    """B14: b+c<40 用校正公式 (|b−c|−1)²/(b+c)。"""
    from medsta.stats.inference import mcnemar_test

    pairs = [(1, 1)] * 30 + [(1, 0)] * 5 + [(0, 1)] * 15 + [(0, 0)] * 30
    frame = pd.DataFrame(pairs, columns=["method_a", "method_b"])
    step = _step("mcnemar_test", ["method_a", "method_b"], row_column="method_a", col_column="method_b")

    result = mcnemar_test(frame, step, step.params)

    assert result["corrected"] is True
    assert result["chi2"] == pytest.approx((abs(5 - 15) - 1) ** 2 / 20, abs=1e-6)


def test_cramers_v_computed_on_fisher_path() -> None:
    """P0: Fisher 精确检验路径也须给出 Cramér's V（基于观测表 χ² 近似），而非恒 0。"""
    from medsta.stats.methods import chi_square

    frame = _fourfold(7, 1, 1, 7)
    result = chi_square(frame, _step("chi_square", ["group", "event"]), {})

    assert result["tier"] == "fisher"
    # 观测表 χ²=16·(7·7−1)²/8⁴=9，n=16，min(shape)−1=1 → V=√(9/16)=0.75
    assert result["cramers_v"] == pytest.approx(0.75, abs=1e-6)


def test_chi_square_embedded_stats_uses_attached_stars() -> None:
    """P0: 结果内嵌表的 significance 须取 attach_significance 之后的星号，而非恒 ns。"""
    from medsta.stats.methods import chi_square

    frame = _fourfold(7, 1, 1, 7)
    result = chi_square(frame, _step("chi_square", ["group", "event"]), {})

    assert result["table"]["stats"][0]["significance"] == result["stars"]
    assert result["table"]["stats"][0]["significance"] != "ns"


def test_multi_rate_pairwise_bonferroni() -> None:
    """B15: 多个样本率整体显著后按 χ² 分割做两两比较，α'=α/C(k,2)。"""
    from medsta.stats.methods import chi_square

    frame = pd.DataFrame(
        {
            "group": ["西药"] * 100 + ["中药"] * 80 + ["中西药"] * 74,
            "effect": ["有效"] * 51 + ["无效"] * 49
            + ["有效"] * 35 + ["无效"] * 45
            + ["有效"] * 59 + ["无效"] * 15,
        }
    )
    step = _step("chi_square", ["group", "effect"])

    result = chi_square(frame, step, step.params)

    pairwise = result["pairwise"]
    assert pairwise["method"] == "chi_square_partition"
    assert pairwise["alpha_prime"] == pytest.approx(0.05 / 3, rel=1e-9)
    assert len(pairwise["rows"]) == 3
    assert all("adjusted_p" in row for row in pairwise["rows"])


def test_group_rate_confidence_interval() -> None:
    """B17: 分组率输出 95%CI，大样本用 Wald、小样本用 Wilson。"""
    from medsta.stats.methods import chi_square

    frame = pd.DataFrame(
        {
            "group": ["A"] * 100 + ["B"] * 30,
            "effect": ["有效"] * 30 + ["无效"] * 70 + ["有效"] * 24 + ["无效"] * 6,
        }
    )
    step = _step("chi_square", ["group", "effect"])

    result = chi_square(frame, step, {"event_value": "有效"})
    rates = {row["group"]: row for row in result["group_rates"]}

    assert rates["A"]["rate"] == pytest.approx(0.30, abs=1e-9)
    assert rates["A"]["rate_column"] == "有效"
    assert rates["A"]["ci_method"] == "wald"
    assert rates["A"]["ci_low"] < 0.30 < rates["A"]["ci_high"]
    assert rates["B"]["ci_method"] == "wilson"
    assert rates["B"]["ci_low"] < 0.80 < rates["B"]["ci_high"]


def test_one_sample_ci_is_narrower_for_one_sided() -> None:
    """B3/B5: 单侧区间只给一侧界值。"""
    rng = np.random.default_rng(7)
    values = rng.normal(5.0, 1.0, 30)
    df = pd.DataFrame({"value": values})

    result = one_sample_test(
        df, _step("one_sample_test", ["value"], mu0=5.0, sides="greater"),
        {"mu0": 5.0, "sides": "greater"},
    )

    assert result["ci95"][0] is not None
    assert result["ci95"][1] is None
    assert result["ci95"][0] < result["mean"]

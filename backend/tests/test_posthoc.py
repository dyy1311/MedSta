"""025 B1–B7：Tukey / Dunnett / LSD-t / Scheffé 事后比较。

教材仅列表 8-9 给出名称与适用范围，无公式；本文件以成熟实现（statsmodels / scipy）
与序关系（Scheffé 比 Tukey 保守）作为基准。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sp_stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd

from medsta.agents.discussion import PlanStep
from medsta.stats import methods


def _step(tool: str, targets: list[str], **params) -> PlanStep:
    return PlanStep(
        title=f"{tool} 步骤",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=params,
        rationale="事后比较口径校验",
    )


def _normal_draws(mean: float, size: int) -> list[float]:
    """确定性近似正态样本（分位数法），避免随机导致的 p 值边界抖动。"""
    quantiles = sp_stats.norm.ppf(np.linspace(0.05, 0.95, size))
    return list(quantiles + mean)


def _three_groups(equal: bool = True) -> pd.DataFrame:
    sizes = (10, 10, 10) if equal else (8, 12, 10)
    rows = []
    for label, mean, size in zip(("A", "B", "C"), (10.0, 12.0, 13.5), sizes):
        rows.extend({"group": label, "value": value} for value in _normal_draws(mean, size))
    return pd.DataFrame(rows)


def _pair_map(result: dict) -> dict[tuple[str, str], dict]:
    return {(row["group_a"], row["group_b"]): row for row in result["pairwise"]["rows"]}


def test_tukey_matches_pairwise_tukeyhsd() -> None:
    """B1: Tukey HSD 的 p 值与 statsmodels pairwise_tukeyhsd 一致（等样本量）。"""
    frame = _three_groups()
    step = _step("anova", ["value"], group_column="group", correction="tukey")

    result = methods.anova(frame, step, step.params)
    ours = _pair_map(result)

    expected = pairwise_tukeyhsd(endog=frame["value"], groups=frame["group"], alpha=0.05)
    labels = list(expected.groupsunique)
    for (first, second), p_value in zip(
        [(labels[i], labels[j]) for i in range(len(labels)) for j in range(i + 1, len(labels))],
        expected.pvalues,
    ):
        assert ours[(first, second)]["p_value"] == pytest.approx(float(p_value), rel=1e-6, abs=1e-9)

    assert result["pairwise"]["method"] == "tukey"


def test_tukey_kramer_supports_unequal_sizes() -> None:
    """B1: 不等样本量走 Tukey-Kramer，p 值仍在 [0,1] 且与 statsmodels 一致。"""
    frame = _three_groups(equal=False)
    step = _step("anova", ["value"], group_column="group", correction="tukey")

    result = methods.anova(frame, step, step.params)
    ours = _pair_map(result)

    expected = pairwise_tukeyhsd(endog=frame["value"], groups=frame["group"], alpha=0.05)
    labels = list(expected.groupsunique)
    for (first, second), p_value in zip(
        [(labels[i], labels[j]) for i in range(len(labels)) for j in range(i + 1, len(labels))],
        expected.pvalues,
    ):
        assert ours[(first, second)]["p_value"] == pytest.approx(float(p_value), rel=1e-6, abs=1e-9)


def test_dunnett_matches_scipy() -> None:
    """B2: Dunnett 只产出对照 vs 各试验组，p 值与 scipy.stats.dunnett 一致。"""
    frame = _three_groups()
    step = _step(
        "anova", ["value"], group_column="group", correction="dunnett", control_group="A"
    )

    result = methods.anova(frame, step, step.params)
    rows = result["pairwise"]["rows"]

    assert result["pairwise"]["method"] == "dunnett"
    assert {row["group_b"] for row in rows} == {"B", "C"}

    control = frame.loc[frame["group"] == "A", "value"].to_numpy()
    expected = sp_stats.dunnett(
        frame.loc[frame["group"] == "B", "value"].to_numpy(),
        frame.loc[frame["group"] == "C", "value"].to_numpy(),
        control=control,
        alternative="two-sided",
        random_state=np.random.default_rng(20261023),
    )
    by_group = {row["group_b"]: row["p_value"] for row in rows}
    assert by_group["B"] == pytest.approx(float(expected.pvalue[0]), rel=1e-6)
    assert by_group["C"] == pytest.approx(float(expected.pvalue[1]), rel=1e-6)


def test_dunnett_requires_control_group() -> None:
    """B3: 未指定对照组时报可读错误并列出可选组名。"""
    frame = _three_groups()
    step = _step("anova", ["value"], group_column="group", correction="dunnett")

    with pytest.raises(ValueError) as excinfo:
        methods.anova(frame, step, step.params)

    message = str(excinfo.value)
    assert "control_group" in message
    assert "A" in message and "B" in message and "C" in message


def test_dunnett_rejects_unknown_control_group() -> None:
    """B3: 对照组名不存在时同样报错。"""
    frame = _three_groups()
    step = _step(
        "anova", ["value"], group_column="group", correction="dunnett", control_group="Z"
    )

    with pytest.raises(ValueError):
        methods.anova(frame, step, step.params)


def test_lsd_is_uncorrected_t() -> None:
    """B4: LSD-t 用合并方差 t、自由度 N−k、不做多重性校正。"""
    frame = _three_groups()
    step = _step("anova", ["value"], group_column="group", correction="lsd")

    result = methods.anova(frame, step, step.params)
    rows = _pair_map(result)

    samples = {label: frame.loc[frame["group"] == label, "value"].to_numpy() for label in "ABC"}
    total = sum(len(values) for values in samples.values())
    df_error = total - 3
    ss_within = sum(((values - values.mean()) ** 2).sum() for values in samples.values())
    ms_error = ss_within / df_error

    for (first, second), row in rows.items():
        values_a, values_b = samples[first], samples[second]
        standard_error = np.sqrt(ms_error * (1 / len(values_a) + 1 / len(values_b)))
        t_value = (values_a.mean() - values_b.mean()) / standard_error
        p_value = 2 * sp_stats.t.sf(abs(t_value), df_error)
        # 输出 statistic 保留 4 位小数，容差按该精度设定
        assert row["statistic"] == pytest.approx(float(t_value), abs=1e-3)
        assert row["p_value"] == pytest.approx(float(p_value), rel=1e-3)
        # LSD 不校正
        assert row["adjusted_p"] == pytest.approx(row["p_value"], rel=1e-9)


def test_scheffe_is_more_conservative_than_tukey() -> None:
    """B5: Scheffé 控制全族误差，p 值恒不小于 Tukey。"""
    frame = _three_groups()
    tukey_step = _step("anova", ["value"], group_column="group", correction="tukey")
    scheffe_step = _step("anova", ["value"], group_column="group", correction="scheffe")

    tukey = _pair_map(methods.anova(frame, tukey_step, tukey_step.params))
    scheffe = _pair_map(methods.anova(frame, scheffe_step, scheffe_step.params))

    for pair, tukey_row in tukey.items():
        assert scheffe[pair]["p_value"] >= tukey_row["p_value"] - 1e-12


def test_posthoc_columns_are_uniform() -> None:
    """B6: 七种事后方法输出同一组列，仅 SNK 额外带 span。"""
    frame = _three_groups()
    required = {
        "group_a", "group_b", "mean_diff", "statistic",
        "p_value", "adjusted_p", "significant", "stars",
    }
    for correction in ("snk", "tukey", "dunnett", "lsd", "scheffe", "holm", "bonferroni"):
        params = {"group_column": "group", "correction": correction}
        if correction == "dunnett":
            params["control_group"] = "A"
        step = _step("anova", ["value"], **params)
        result = methods.anova(frame, step, step.params)

        assert result["pairwise"]["method"] in {correction, "snk"}
        for row in result["pairwise"]["rows"]:
            assert required <= set(row), correction
            assert row["method"] == result["pairwise"]["method"]


def test_kruskal_ignores_parametric_posthoc() -> None:
    """B7: Kruskal 路径不进入参数事后，退回 Dunn 并说明原因。"""
    rng = np.random.default_rng(25)
    frame = pd.DataFrame(
        {
            "group": ["A"] * 12 + ["B"] * 12 + ["C"] * 12,
            "value": np.concatenate(
                [
                    rng.lognormal(1.0, 0.9, 12),
                    rng.lognormal(1.8, 0.9, 12),
                    rng.lognormal(2.2, 0.9, 12),
                ]
            ),
        }
    )
    step = _step("anova", ["value"], group_column="group", correction="tukey")

    result = methods.anova(frame, step, step.params)

    assert result["test"] == "kruskal"
    assert result["pairwise"]["method"] == "dunn"
    assert "Dunn" in result["multiplicity_warning"]

"""显著性规范：统一的 α 判定、星号标注与多重比较校正。"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as sp_stats


def significance_label(p_value: float, alpha: float = 0.05) -> dict:
    """p 值 → 显著性判定：星号按常规阈值，significant 按用户 α。"""
    if p_value is None or (isinstance(p_value, float) and np.isnan(p_value)):
        return {"significant": False, "stars": "ns"}
    stars = "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else "ns"
    return {"significant": bool(p_value < alpha), "stars": stars}


def p_adjust(p_values: list[float], method: str = "holm") -> list[float]:
    """多重比较 p 值校正：holm（默认）/ bonferroni / none。"""
    values = np.asarray(p_values, dtype=float)
    n = len(values)
    if n == 0 or method == "none":
        return list(values)
    if method == "bonferroni":
        return list(np.minimum(values * n, 1.0))
    if method != "holm":
        raise ValueError(f"未知校正方法：{method}")
    order = np.argsort(values)
    sorted_p = values[order]
    adjusted = sorted_p * (n - np.arange(n))
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.minimum(adjusted, 1.0)
    result = np.empty(n)
    result[order] = adjusted
    return list(result)


def attach_significance(result: dict, p_key: str, alpha: float) -> dict:
    """就地给含 p_key 的结果 dict 附加 alpha/significant/stars。"""
    raw_p = result.get(p_key)
    label = significance_label(float(raw_p) if raw_p is not None else 1.0, alpha)
    result["alpha"] = alpha
    result.update(label)
    return result


def bonferroni_alpha(alpha: float, comparisons: int) -> float:
    """Bonferroni 调整后的检验水准（教材 §9 公式 9-10/9-11）。"""
    return alpha / max(int(comparisons), 1)


def snk_q_pvalue(
    mean_a: float,
    mean_b: float,
    n_a: int,
    n_b: int,
    ms_error: float,
    df_error: float,
    span: int,
) -> tuple[float, float]:
    """SNK-q 检验（教材 §8 公式 8-9）：返回 (q 值, p 值)。

    span 为两对比组在均值排序中所包含的组数（相邻两组为 2）。
    """
    if n_a <= 0 or n_b <= 0:
        raise ValueError("SNK-q 需要每组至少 1 个观测")
    if ms_error <= 0:
        return 0.0, 1.0
    standard_error = math.sqrt(ms_error / 2 * (1 / n_a + 1 / n_b))
    q_value = abs(float(mean_a) - float(mean_b)) / standard_error
    p_value = float(sp_stats.studentized_range.sf(q_value, max(int(span), 2), df_error))
    return float(q_value), p_value


def tukey_q_pvalue(
    mean_a: float,
    mean_b: float,
    n_a: int,
    n_b: int,
    ms_error: float,
    df_error: float,
    groups: int,
) -> tuple[float, float]:
    """Tukey HSD（Tukey-Kramer）：返回 (q 值, p 值)。

    与 SNK 的唯一差别是 studentized range 的组数固定为总组数 k，而非两组的位次跨度，
    因此 Tukey 更保守。不等样本量时即为 Tukey-Kramer。
    """
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Tukey HSD 需要每组至少 1 个观测")
    if ms_error <= 0:
        return 0.0, 1.0
    standard_error = math.sqrt(ms_error / 2 * (1 / n_a + 1 / n_b))
    q_value = abs(float(mean_a) - float(mean_b)) / standard_error
    p_value = float(sp_stats.studentized_range.sf(q_value, max(int(groups), 2), df_error))
    return float(q_value), p_value


def lsd_t_pvalue(
    mean_a: float,
    mean_b: float,
    n_a: int,
    n_b: int,
    ms_error: float,
    df_error: float,
) -> tuple[float, float]:
    """LSD-t：成对合并方差 t，不做多重性校正（教材表 8-9：理论上只适合两组）。"""
    if n_a <= 0 or n_b <= 0:
        raise ValueError("LSD-t 需要每组至少 1 个观测")
    if ms_error <= 0:
        return 0.0, 1.0
    standard_error = math.sqrt(ms_error * (1 / n_a + 1 / n_b))
    t_value = (float(mean_a) - float(mean_b)) / standard_error
    p_value = float(2 * sp_stats.t.sf(abs(t_value), df_error))
    return float(t_value), p_value


def scheffe_pvalue(
    mean_a: float,
    mean_b: float,
    n_a: int,
    n_b: int,
    ms_error: float,
    df_error: float,
    groups: int,
) -> tuple[float, float]:
    """Scheffé 两两比较：返回 (F 值, p 值)。

    `F = diff² / (MSE·(1/na+1/nb)·(k−1))`，`p = F.sf(F, k−1, df_error)`。
    控制全族误差率，p 值恒不小于 Tukey。
    """
    if n_a <= 0 or n_b <= 0:
        raise ValueError("Scheffé 需要每组至少 1 个观测")
    if ms_error <= 0 or groups < 2:
        return 0.0, 1.0
    variance = ms_error * (1 / n_a + 1 / n_b) * (groups - 1)
    f_value = (float(mean_a) - float(mean_b)) ** 2 / variance
    p_value = float(sp_stats.f.sf(f_value, groups - 1, df_error))
    return float(f_value), p_value


def snk_step_down(rows: list[dict], alpha: float = 0.05) -> list[dict]:
    """教材 §8-4 逐步规则：跨度最大的比较不显著时，更小跨度不再判为显著。

    原始 p 值全部保留，`significant` 按规则给出，被规则拦下的行标 `step_down=True`。
    """
    indexed = list(enumerate(rows))
    ordered = sorted(indexed, key=lambda item: item[1].get("span", 2), reverse=True)
    decided: dict[int, dict] = {}
    blocked = False
    for index, row in ordered:
        if blocked:
            decided[index] = {**row, "significant": False, "step_down": True}
        elif float(row.get("p_value", 1.0)) > alpha:
            decided[index] = {**row, "significant": False, "step_down": False}
            blocked = True
        else:
            decided[index] = {**row, "significant": True, "step_down": False}
    return [decided[index] for index in range(len(rows))]


def dunn_pvalue(
    rank_mean_a: float,
    rank_mean_b: float,
    n_a: int,
    n_b: int,
    total_n: int,
    ties_correction: float = 1.0,
) -> tuple[float, float]:
    """Dunn 事后检验（Kruskal-Wallis 之后）：返回 (z 值, 双侧 p 值)。

    教材 §10 未给公式，此处采用通用 Dunn 法；ties_correction 为
    `1 − Σ(t³−t)/(N³−N)`，无结时取 1。
    """
    variance = (
        total_n * (total_n + 1) / 12 * (1 / n_a + 1 / n_b) * max(ties_correction, 1e-12)
    )
    if variance <= 0:
        return 0.0, 1.0
    z_value = (float(rank_mean_a) - float(rank_mean_b)) / math.sqrt(variance)
    p_value = float(2 * (1 - sp_stats.norm.cdf(abs(z_value))))
    return float(z_value), p_value

"""显著性规范：统一的 α 判定、星号标注与多重比较校正。"""
from __future__ import annotations

import numpy as np


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
    label = significance_label(result.get(p_key), alpha)
    result["alpha"] = alpha
    result.update(label)
    return result

"""统计描述与医学参考值范围（spec 023）。

依据《医学统计学》第 8 版（李康、贺佳）第二、三章：
- 分布形态判定 → 推荐描述指标（x̄±s / M(P25~P75) / G）；
- 变异指标（标准差、IQR、极差、变异系数）；
- 参考值范围的正态法、百分位数法与对数正态法。

所有判定与计算均为宿主确定性逻辑，模型只负责选方法与解读结论。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from medsta.stats.notes import METHOD_NOTES

_SKEW_LIMIT = 1.0
_MEAN_EPS = 1e-12
_DOMINANT_SHARE = 0.5
_LARGE_SAMPLE = 500


@dataclass(frozen=True)
class DistributionDecision:
    kind: Literal["normal", "log_normal", "skewed", "insufficient"]
    recommended: str
    reason: str
    skewness: float | None = None
    shapiro_p: float | None = None


def _clean(values: Any) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    return data[np.isfinite(data)]


def classify_distribution(values: Any, *, alpha: float = 0.05) -> DistributionDecision:
    """按教材口径判定分布形态，并给出推荐的描述指标。"""
    data = _clean(values)
    n = len(data)
    if n < 3:
        return DistributionDecision(
            "insufficient", "", f"有效样本仅 {n} 例，不足以判定分布形态；仅报告例数与极值", None, None
        )
    if len(np.unique(data)) < 3:
        return DistributionDecision(
            "insufficient", "", "有效取值不足 3 个不同数值，无法进行正态性判定", None, None
        )

    skewness = float(sp_stats.skew(data, bias=False))
    shapiro_p = float(sp_stats.shapiro(data).pvalue)

    counts = np.unique(data, return_counts=True)[1]
    dominant_share = float(counts.max()) / n
    if dominant_share > _DOMINANT_SHARE:
        return DistributionDecision(
            "skewed",
            "M(P25~P75)",
            f"单一取值占 {dominant_share:.0%}（n={n}），呈离散堆积，按偏态报告中位数与四分位数间距",
            skewness,
            shapiro_p,
        )

    # 大样本时 Shapiro 对微小偏离过度敏感（教材 §3 亦提示），改以偏度为主判据
    normal_by_skew = abs(skewness) <= _SKEW_LIMIT
    if normal_by_skew and (n >= _LARGE_SAMPLE or shapiro_p > alpha):
        reason = (
            f"偏度 {skewness:.2f}（n={n}≥{_LARGE_SAMPLE}，以偏度为主）→ 按正态分布报告均数与标准差"
            if n >= _LARGE_SAMPLE
            else f"偏度 {skewness:.2f} 且 Shapiro P={shapiro_p:.3f}>α，按正态分布报告均数与标准差"
        )
        return DistributionDecision("normal", "x̄±s", reason, skewness, shapiro_p)

    if np.all(data > 0):
        log_values = np.log(data)
        log_skew = float(sp_stats.skew(log_values, bias=False))
        # 离散分级数据（滴度、评分）取值很少，Shapiro 的连续正态假设不成立，改用偏度判定
        if len(np.unique(log_values)) <= 6:
            log_p = 1.0
        else:
            log_p = float(sp_stats.shapiro(log_values).pvalue)
        if abs(log_skew) <= _SKEW_LIMIT and log_p > alpha:
            return DistributionDecision(
                "log_normal",
                "G",
                f"原始值偏态（Shapiro P={shapiro_p:.3f}），对数变换后偏度 {log_skew:.2f}，按对数正态报告几何均数",
                skewness,
                shapiro_p,
            )

    return DistributionDecision(
        "skewed",
        "M(P25~P75)",
        f"偏度 {skewness:.2f}，Shapiro P={shapiro_p:.3f}≤α，按偏态分布报告中位数与四分位数间距",
        skewness,
        shapiro_p,
    )


def _geometric_mean(data: np.ndarray) -> float | None:
    """几何均数：观察值必须全部为正（教材 §2 二）。"""
    if len(data) == 0 or np.any(data <= 0):
        return None
    return float(np.exp(np.mean(np.log(data))))


def _modes(data: np.ndarray) -> float | list[float] | None:
    values, counts = np.unique(data, return_counts=True)
    top = counts.max()
    winners = values[counts == top]
    if len(winners) == len(values):
        return None
    if len(winners) == 1:
        return float(winners[0])
    return [float(value) for value in winners]


def _describe_values(values: Any, *, alpha: float = 0.05) -> dict[str, Any]:
    """一组观察值的完整描述口径（教材 §2 第二、三节）。"""
    data = _clean(values)
    n = len(data)
    if n == 0:
        return {
            "n": 0, "mean": None, "sd": None, "cv": None, "median": None,
            "q25": None, "q75": None, "iqr": None, "min": None, "max": None,
            "range": None, "mode": None, "skewness": None, "geometric_mean": None,
            "distribution": "insufficient", "recommended": "", "reason": "无有效数值",
        }

    mean = float(data.mean())
    sd = float(data.std(ddof=1)) if n > 1 else None
    cv = round(sd / mean * 100, 4) if sd is not None and abs(mean) > _MEAN_EPS else None
    q25, median, q75 = (float(value) for value in np.percentile(data, [25, 50, 75]))
    geometric = _geometric_mean(data)
    decision = classify_distribution(data, alpha=alpha)

    reason = decision.reason
    if geometric is None and np.any(data <= 0):
        reason += "；含 0 或负值，几何均数不适用"

    return {
        "n": n,
        "mean": round(mean, 4),
        "sd": round(sd, 4) if sd is not None else None,
        "cv": cv,
        "median": round(median, 4),
        "q25": round(q25, 4),
        "q75": round(q75, 4),
        "iqr": round(q75 - q25, 4),
        "min": round(float(data.min()), 4),
        "max": round(float(data.max()), 4),
        "range": round(float(data.max() - data.min()), 4),
        "mode": _modes(data),
        "skewness": round(float(sp_stats.skew(data, bias=False)), 4) if n > 2 else None,
        "geometric_mean": round(geometric, 4) if geometric is not None else None,
        "distribution": decision.kind,
        "recommended": decision.recommended,
        "reason": reason,
    }


_TABLE_COLUMNS = (
    "column", "n", "mean", "sd", "cv", "median", "q25", "q75", "iqr",
    "min", "max", "range", "distribution", "recommended",
)


def descriptive_stats(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """统计描述：逐列完整指标 + 分布形态推荐，可按分组分层。"""
    group_by = params.get("group_by")
    alpha = float(params.get("alpha", 0.05) or 0.05)
    columns: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []

    for column in step.target_columns:
        entry = _describe_values(pd.to_numeric(df[column], errors="coerce"), alpha=alpha)
        if group_by and group_by in df.columns:
            entry["group_column"] = group_by
            entry["groups"] = {
                str(key): _describe_values(
                    pd.to_numeric(frame[column], errors="coerce"), alpha=alpha
                )
                for key, frame in df.groupby(group_by, sort=False)
            }
        columns[column] = entry
        rows.append({"column": column, **{key: entry.get(key) for key in _TABLE_COLUMNS if key != "column"}})

    return {
        "columns": columns,
        "table": {"columns": list(_TABLE_COLUMNS), "rows": rows},
        "method_note": METHOD_NOTES["descriptive_stats"],
    }


_PERCENTAGES = (90, 95, 99)
_SIDES = ("two", "one_lower", "one_upper")


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def _z_value(percentage: int, sides: str) -> float:
    """标准正态界值：双侧取 1−α/2 分位，单侧取 1−α 分位（教材表 3-1）。"""
    proportion = percentage / 100
    if sides == "two":
        return float(sp_stats.norm.ppf(1 - (1 - proportion) / 2))
    return float(sp_stats.norm.ppf(proportion))


def _normal_bounds(
    mean: float, sd: float, *, percentage: int, sides: str
) -> tuple[float | None, float | None, float]:
    z_value = _z_value(percentage, sides)
    if sides == "two":
        return mean - z_value * sd, mean + z_value * sd, z_value
    if sides == "one_lower":
        return mean - z_value * sd, None, z_value
    return None, mean + z_value * sd, z_value


def _percentile_bounds(percentage: int, sides: str) -> tuple[float | None, float | None]:
    if sides == "two":
        tail = (100 - percentage) / 2
        return tail, 100 - tail
    if sides == "one_lower":
        return float(100 - percentage), None
    return None, float(percentage)


def compute_reference_range(
    values: Any,
    *,
    percentage: int = 95,
    sides: str = "two",
    method: str = "auto",
    alpha: float = 0.05,
) -> dict[str, Any]:
    """医学参考值范围（教材 §3 表 3-1）。"""
    data = _clean(values)
    n = len(data)
    if n < 3:
        raise ValueError(f"参考值范围至少需要 3 个有效观测，当前 {n}")
    if percentage not in _PERCENTAGES:
        raise ValueError(f"百分数只支持 {_PERCENTAGES}，收到 {percentage}")
    if sides not in _SIDES:
        raise ValueError(f"单双侧只支持 {_SIDES}，收到 {sides}")
    if method not in ("auto", "normal", "percentile", "log_normal"):
        raise ValueError(f"未知计算方法：{method}")

    decision = classify_distribution(data, alpha=alpha)
    resolved = method
    if method == "auto":
        resolved = {
            "normal": "normal",
            "log_normal": "log_normal",
        }.get(decision.kind, "percentile")

    warnings: list[str] = []
    if resolved == "percentile" and n < 100:
        warnings.append("百分位数法在 n<100 时两端界值不稳定（教材 §3 二），建议增大样本")
    if resolved == "normal" and n < 30:
        warnings.append("正态法在 n<30 时结果不稳定，建议增大样本或改用百分位数法")

    result: dict[str, Any] = {
        "percentage": percentage,
        "sides": sides,
        "n": n,
        "method": resolved,
        "distribution": decision.kind,
        "warnings": warnings,
    }

    if resolved == "normal":
        lower, upper, z_value = _normal_bounds(
            float(data.mean()), float(data.std(ddof=1)), percentage=percentage, sides=sides
        )
        result.update(
            {"lower": _round_or_none(lower), "upper": _round_or_none(upper), "z_value": round(z_value, 4)}
        )
    elif resolved == "log_normal":
        # 强制对数正态法时必须显式拒绝非正值：np.log 产生的 NaN 会静默
        # 传播到 lower/upper，威胁「严格 JSON」出口契约（批次11；auto 路径原有正性门）
        if not bool(np.all(data > 0)):
            raise ValueError("对数正态法要求数据全部为正；含 0 或负值请改用百分位数法")
        log_values = np.log(data)
        lower, upper, z_value = _normal_bounds(
            float(log_values.mean()),
            float(log_values.std(ddof=1)),
            percentage=percentage,
            sides=sides,
        )
        result.update(
            {
                "lower": _round_or_none(None if lower is None else float(np.exp(lower))),
                "upper": _round_or_none(None if upper is None else float(np.exp(upper))),
                "z_value": round(z_value, 4),
                "scale": "对数值计算后取反对数还原",
            }
        )
    else:
        low_percentile, high_percentile = _percentile_bounds(percentage, sides)
        lower = float(np.percentile(data, low_percentile)) if low_percentile is not None else None
        upper = float(np.percentile(data, high_percentile)) if high_percentile is not None else None
        result.update(
            {
                "lower": _round_or_none(lower),
                "upper": _round_or_none(upper),
                "percentiles": [low_percentile, high_percentile],
            }
        )

    result["method_note"] = METHOD_NOTES["reference_range"]
    return result


_REFERENCE_COLUMNS = ("column", "method", "percentage", "sides", "n", "lower", "upper")


def reference_range(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """工具入口：对目标列计算参考值范围，交付为单行表格。"""
    column = step.target_columns[0]
    payload = compute_reference_range(
        pd.to_numeric(df[column], errors="coerce"),
        percentage=int(params.get("percentage", 95) or 95),
        sides=str(params.get("sides", "two") or "two"),
        method=str(params.get("method", "auto") or "auto"),
        alpha=float(params.get("alpha", 0.05) or 0.05),
    )
    payload["column"] = column
    payload["table"] = {
        "columns": list(_REFERENCE_COLUMNS),
        "rows": [{key: payload.get(key) for key in _REFERENCE_COLUMNS}],
    }
    return payload

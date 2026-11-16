"""生存分析（spec 027）：Kaplan-Meier、log-rank / Breslow、Cox、RMST。

依据《医学统计学》第 8 版第十四章。RMST 与 Schoenfeld 检验教材未给公式，
按外部标准实现并在 method_note 中标注来源。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from medsta.stats.notes import METHOD_NOTES
from medsta.stats.significance import attach_significance

_Z_95 = 1.959964


def _sorted_by_time_event_first(time: np.ndarray, event: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """时间升序；同一时间点完全数据排在删失数据之前（教材 §14-2 规则）。"""
    order = np.lexsort((np.where(event == 1, 0, 1), time))
    return time[order], event[order]


def km_estimate(time: Any, event: Any) -> dict[str, Any]:
    """Kaplan-Meier 乘积极限估计（教材公式 14-4/14-5/14-6）。"""
    times = np.asarray(time, dtype=float)
    events = np.asarray(event, dtype=int)
    times, events = _sorted_by_time_event_first(times, events)

    at_risk = int(len(times))
    survival = 1.0
    greenwood_sum = 0.0
    points: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    ci_truncated = False

    index = 0
    while index < len(times):
        current = float(times[index])
        block_end = index
        while block_end < len(times) and times[block_end] == current:
            block_end += 1
        block_events = int(events[index:block_end].sum())
        block_censored = int((block_end - index) - block_events)

        if block_events > 0:
            n_at_risk = at_risk
            survival *= 1 - block_events / n_at_risk
            if n_at_risk > block_events:
                greenwood_sum += block_events / (n_at_risk * (n_at_risk - block_events))
            se = survival * math.sqrt(greenwood_sum)
            low, high, truncated = _ci(survival, se)
            ci_truncated = ci_truncated or truncated
            points.append(
                {
                    "time": current,
                    "n_at_risk": n_at_risk,
                    "events": block_events,
                    "censored": 0,
                    "survival": survival,
                    "se": se,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
            risk_rows.append(
                {"time": current, "n_at_risk": n_at_risk, "events": block_events, "censored": 0}
            )
            at_risk -= block_events

        if block_censored > 0:
            n_at_risk = at_risk
            se = survival * math.sqrt(greenwood_sum)
            low, high, truncated = _ci(survival, se)
            ci_truncated = ci_truncated or truncated
            points.append(
                {
                    "time": current,
                    "n_at_risk": n_at_risk,
                    "events": 0,
                    "censored": block_censored,
                    "survival": survival,
                    "se": se,
                    "ci_low": low,
                    "ci_high": high,
                }
            )
            risk_rows.append(
                {"time": current, "n_at_risk": n_at_risk, "events": 0, "censored": block_censored}
            )
            at_risk -= block_censored

        index = block_end

    median, reached = _median_survival(points)
    return {
        "n": int(len(times)),
        "events": int(events.sum()),
        "censored": int(len(times) - events.sum()),
        "points": points,
        "median_survival": median,
        "median_reached": reached,
        "median_survival_note": "" if reached else "随访期内生存率未降至 50%",
        "ci_truncated": ci_truncated,
        "risk_table": {
            "columns": ["time", "n_at_risk", "events", "censored"],
            "rows": risk_rows,
        },
    }


def _ci(survival: float, se: float) -> tuple[float, float, bool]:
    low = survival - _Z_95 * se
    high = survival + _Z_95 * se
    truncated = low < 0 or high > 1
    return max(0.0, low), min(1.0, high), truncated


def _median_survival(points: list[dict[str, Any]]) -> tuple[float | None, bool]:
    if not points:
        return None, False
    if points[0]["survival"] <= 0.5:
        return points[0]["time"], True
    for previous, current in zip(points, points[1:]):
        if previous["survival"] > 0.5 >= current["survival"]:
            span = previous["survival"] - current["survival"]
            if span <= 0:
                return current["time"], True
            ratio = (previous["survival"] - 0.5) / span
            median = previous["time"] + ratio * (current["time"] - previous["time"])
            return float(median), True
    return None, False


def survival_analysis(df: pd.DataFrame, step: Any, params: dict) -> dict[str, Any]:
    """工具入口：KM / log-rank / Cox / RMST 的统一分派。"""
    time_column = params.get("time_col") or (
        step.target_columns[0] if step.target_columns else None
    )
    event_column = params.get("event_col") or (
        step.target_columns[1] if len(step.target_columns) > 1 else None
    )
    if not time_column or not event_column:
        raise ValueError("生存分析需要 time_col（随访时间）与 event_col（事件指示，1=事件/0=删失）")
    if time_column not in df.columns or event_column not in df.columns:
        raise ValueError(f"列不存在：{time_column} / {event_column}")

    group_column = params.get("group_col")
    covariates = params.get("covariates") or []
    if isinstance(covariates, str):
        covariates = [covariates]
    method = str(params.get("method", "auto") or "auto")
    test = str(params.get("test", "logrank") or "logrank")
    tau = params.get("tau")
    alpha = float(params.get("alpha", 0.05) or 0.05)

    columns = [time_column, event_column]
    for extra in [group_column, *covariates]:
        if extra and extra not in columns:
            columns.append(extra)
    frame = df[columns].copy()
    frame[time_column] = pd.to_numeric(frame[time_column], errors="coerce")
    frame = frame.dropna(subset=[time_column, event_column])

    times = frame[time_column].to_numpy(dtype=float)
    if np.any(times < 0):
        raise ValueError("随访时间不能为负值")
    raw_events = frame[event_column]
    unique_events = set(pd.unique(raw_events).tolist())
    if not unique_events <= {0, 1, 0.0, 1.0, True, False}:
        raise ValueError(
            f"事件列「{event_column}」只能取 0/1（1=事件，0=删失），当前取值：{sorted(unique_events)}"
        )
    events = raw_events.to_numpy(dtype=int)
    if events.sum() == 0:
        raise ValueError("事件数为 0（全部删失），无法估计生存曲线")

    if method == "auto":
        method = "cox" if covariates else ("logrank" if group_column else "km")
    if method not in ("km", "logrank", "cox"):
        raise ValueError(f"未知分析方法：{method}（可选 auto/km/logrank/cox）")

    result: dict[str, Any] = {
        "time_column": time_column,
        "event_column": event_column,
        "method": method,
        "n": int(len(times)),
        "events": int(events.sum()),
        "censored": int(len(times) - events.sum()),
    }

    if method == "km":
        estimate = km_estimate(times, events)
        result.update(
            {
                "median_survival": estimate["median_survival"],
                "median_reached": estimate["median_reached"],
                "median_survival_note": estimate["median_survival_note"],
                "ci_truncated": estimate["ci_truncated"],
                "points": estimate["points"],
            }
        )
        if group_column:
            grouped = {}
            for label, chunk in frame.groupby(frame[group_column].astype(str), sort=False):
                single = km_estimate(
                    chunk[time_column].to_numpy(dtype=float),
                    chunk[event_column].to_numpy(dtype=int),
                )
                grouped[str(label)] = {
                    "n": single["n"],
                    "events": single["events"],
                    "median_survival": single["median_survival"],
                    "median_reached": single["median_reached"],
                    "points": single["points"],
                }
            result["groups"] = grouped
        result["table"] = {
            "columns": ["time", "n_at_risk", "events", "censored", "survival", "se"],
            "rows": [
                {
                    "time": point["time"],
                    "n_at_risk": point["n_at_risk"],
                    "events": point["events"],
                    "censored": point["censored"],
                    "survival": round(point["survival"], 6),
                    "se": round(point["se"], 6),
                }
                for point in estimate["points"]
            ],
        }
        result["p_value"] = None
    elif method == "logrank":
        if not group_column:
            raise ValueError("log-rank 检验需要 group_col（分组变量）")
        labels = frame[group_column].astype(str).to_numpy()
        comparison = logrank_test(times, events, labels, weight=test)
        result.update(comparison)
        result["group_column"] = group_column
        result["table"] = {
            "columns": ["group", "observed", "expected"],
            "rows": [
                {
                    "group": label,
                    "observed": round(comparison["observed"][index], 4),
                    "expected": round(comparison["expected"][index], 4),
                }
                for index, label in enumerate(comparison["groups"])
            ],
        }
        result["p_value"] = comparison["p_value"]
    else:
        if not covariates:
            raise ValueError("Cox 回归需要 covariates（至少 1 个协变量）")
        model = cox_fit(times, events, frame[covariates])
        result.update(model)
        result["table"] = {
            "columns": ["term", "coef", "se", "hr", "hr_ci_low", "hr_ci_high", "p_value"],
            "rows": [
                {
                    "term": row["term"],
                    "coef": round(row["coef"], 4),
                    "se": round(row["se"], 4),
                    "hr": round(row["hr"], 4),
                    "hr_ci_low": round(row["hr_ci_low"], 4),
                    "hr_ci_high": round(row["hr_ci_high"], 4),
                    "p_value": row["p_value"],
                }
                for row in model["coefficients"]
            ],
        }
        result["p_value"] = model["lr_test"]["p_value"]

    rmst_summary: dict[str, Any] = {}
    if group_column:
        grouped = list(frame.groupby(frame[group_column].astype(str), sort=False))
        # 未显式指定 tau 时以「各组最大随访最小值」统一截断，保证组间 RMST 可比
        common_tau = (
            float(tau)
            if tau
            else min(float(chunk[time_column].max()) for _, chunk in grouped)
        )
        per_group = {}
        for label, chunk in grouped:
            per_group[str(label)] = rmst(
                chunk[time_column].to_numpy(dtype=float),
                chunk[event_column].to_numpy(dtype=int),
                tau=common_tau,
            )
        rmst_summary["groups"] = per_group
        labels = list(per_group)
        if len(labels) == 2:
            first, second = per_group[labels[0]], per_group[labels[1]]
            rmst_summary["difference"] = {
                "groups": [labels[0], labels[1]],
                "value": first["rmst"] - second["rmst"],
            }
    else:
        rmst_summary["overall"] = rmst(times, events, tau=float(tau) if tau else None)
    result["rmst"] = rmst_summary

    notes = []
    if method == "km":
        notes.append("KM 乘积极限估计：删失个体在删失前仍计入风险集，与缺失值处理不同")
    elif method == "logrank":
        notes.append(
            "log-rank 对整条曲线加权（晚期差异更敏感）；Breslow 以风险人数加权（早期差异更敏感）"
        )
    else:
        violated = [item["term"] for item in model["ph_check"] if item["violated"]]
        if violated:
            notes.append(
                f"比例风险假定可能不满足（{', '.join(violated)}）；可考虑分层 Cox 或时依协变量"
            )
    result["strategy"] = {
        "steps": [
            f"样本 {len(times)} 例，事件 {int(events.sum())} 例，删失 {int(len(times) - events.sum())} 例",
            *notes,
        ],
        "final_method": f"survival_{method}",
        "alternative": "次优：参数生存模型（Weibull/exponential），需分布假定成立",
    }
    result["method_note"] = METHOD_NOTES["survival_analysis"]
    return attach_significance(result, "p_value", alpha) if result.get("p_value") is not None else result


def _schoenfeld_check(
    model: Any, columns: Any, times: np.ndarray, events: np.ndarray
) -> list[dict[str, Any]]:
    """Schoenfeld 残差与时间的 Spearman 相关（教材未给，按外部标准实现）。

    statsmodels 0.14 的残差与 nobs 对齐、删失行置 0：必须按事件掩码排除，
    否则伪 0 残差与删失的大时间一并进入 Spearman，rho 被稀释（M8）。
    """
    raw = getattr(model, "schoenfeld_residuals", None)
    if raw is None:
        return []
    residuals = np.asarray(raw() if callable(raw) else raw, dtype=float)
    if residuals.ndim == 1:
        residuals = residuals.reshape(-1, 1)
    checks: list[dict[str, Any]] = []
    for index, term in enumerate(columns):
        if index >= residuals.shape[1]:
            break
        values = residuals[:, index]
        valid = np.isfinite(values)
        if len(values) == len(events):
            valid = valid & (np.asarray(events) == 1)
        if valid.sum() < 3:
            checks.append({"term": str(term), "rho": 0.0, "p_value": 1.0, "violated": False})
            continue
        rho, p_value = sp_stats.spearmanr(values[valid], times[valid])
        checks.append(
            {
                "term": str(term),
                "rho": float(rho),
                "p_value": float(p_value),
                "violated": bool(float(p_value) < 0.05),
            }
        )
    return checks


def cox_fit(time: Any, event: Any, covariates: pd.DataFrame) -> dict[str, Any]:
    """Cox 比例风险回归（教材公式 14-11~14-15）。"""
    from statsmodels.duration.hazard_regression import PHReg

    times = np.asarray(time, dtype=float)
    events = np.asarray(event, dtype=int)
    frame = covariates.astype(float).reset_index(drop=True)
    if frame.shape[1] == 0:
        raise ValueError("Cox 回归至少需要 1 个协变量")
    for column in frame.columns:
        if frame[column].nunique() <= 1:
            raise ValueError(f"协变量「{column}」为常数，无法估计回归系数")

    model = PHReg(times, frame.to_numpy(), status=events, ties="efron").fit()
    null_model = PHReg(times, np.ones((len(times), 1)), status=events, ties="efron").fit()
    interval = model.conf_int()

    coefficients: list[dict[str, Any]] = []
    for index, term in enumerate(frame.columns):
        coef = float(model.params[index])
        se = float(model.bse[index])
        coefficients.append(
            {
                "term": str(term),
                "coef": coef,
                "se": se,
                "hr": math.exp(coef),
                "hr_ci_low": math.exp(float(interval[index][0])),
                "hr_ci_high": math.exp(float(interval[index][1])),
                "wald_chi2": (coef / se) ** 2 if se else None,
                "p_value": float(model.pvalues[index]),
                "direction": "危险因素" if coef > 0 else ("保护因素" if coef < 0 else "无关联"),
            }
        )

    parameter_count = frame.shape[1]
    lr_chi2 = 2 * (float(model.llf) - float(null_model.llf))
    lr_test = {
        "chi2": lr_chi2,
        "df": parameter_count,
        "p_value": float(sp_stats.chi2.sf(lr_chi2, parameter_count)),
    }

    score_statistic = getattr(model, "score", None)
    if score_statistic is None or callable(score_statistic):
        score_test = {
            "chi2": None,
            "p_value": None,
            "note": "statsmodels 未提供 Score 统计量，已输出 LR 与 Wald 检验",
        }
    else:
        score_chi2 = float(score_statistic)
        score_test = {
            "chi2": score_chi2,
            "p_value": float(sp_stats.chi2.sf(score_chi2, parameter_count)),
            "note": "",
        }

    return {
        "n": int(len(times)),
        "events": int(events.sum()),
        "coefficients": coefficients,
        "lr_test": lr_test,
        "score_test": score_test,
        "ph_check": _schoenfeld_check(model, frame.columns, times, events),
    }


def rmst(time: Any, event: Any, *, tau: float | None = None) -> dict[str, Any]:
    """限制性平均生存时间（教材未给公式，按标准定义以阶梯曲线积分）。"""
    times = np.asarray(time, dtype=float)
    events = np.asarray(event, dtype=int)
    maximum = float(times.max())
    limit = maximum if tau is None else float(tau)
    truncated = limit > maximum

    estimate = km_estimate(times, events)
    points = [point for point in estimate["points"] if point["time"] <= limit]

    area = 0.0
    cumulative: list[float] = []
    previous_time, previous_survival = 0.0, 1.0
    for point in points:
        area += previous_survival * (point["time"] - previous_time)
        cumulative.append(area)
        previous_time, previous_survival = point["time"], point["survival"]
    if limit > previous_time:
        area += previous_survival * (limit - previous_time)

    variance = 0.0
    for index, point in enumerate(points):
        if point["events"] == 0:
            continue
        at_risk, deaths = point["n_at_risk"], point["events"]
        if at_risk <= deaths:
            continue
        remaining = area - cumulative[index]
        variance += (remaining**2) * deaths / (at_risk * (at_risk - deaths))
    standard_error = math.sqrt(max(variance, 0.0))

    return {
        "tau": limit,
        "rmst": float(area),
        "se": standard_error,
        "ci_low": max(0.0, area - _Z_95 * standard_error),
        "ci_high": min(limit, area + _Z_95 * standard_error),
        "truncated": truncated,
        "max_followup": maximum,
    }


def logrank_test(
    time: Any, event: Any, group: Any, *, weight: str = "logrank"
) -> dict[str, Any]:
    """log-rank（Mantel-Cox）或 Breslow 检验（教材公式 14-8/14-9）。"""
    times = np.asarray(time, dtype=float)
    events = np.asarray(event, dtype=int)
    labels = list(dict.fromkeys(np.asarray(group).tolist()))
    k = len(labels)
    if k < 2:
        raise ValueError("生存率比较至少需要 2 组")
    if weight not in ("logrank", "breslow"):
        raise ValueError(f"未知检验类型：{weight}（可选 logrank/breslow）")

    groups = np.asarray(group)
    observed = np.zeros(k)
    expected = np.zeros(k)
    variance = np.zeros((k, k))

    for moment in np.unique(times[events == 1]):
        at_risk_mask = times >= moment
        total_at_risk = int(at_risk_mask.sum())
        total_events = int(((times == moment) & (events == 1)).sum())
        if total_at_risk < 2 or total_events == 0:
            continue
        counts = np.array(
            [int(((times >= moment) & (groups == label)).sum()) for label in labels]
        )
        deaths = np.array(
            [int(((times == moment) & (events == 1) & (groups == label)).sum()) for label in labels]
        )
        factor = total_events * (total_at_risk - total_events) / (total_at_risk - 1)
        proportion = counts / total_at_risk
        weight_value = 1.0 if weight == "logrank" else float(total_at_risk)

        observed += weight_value * deaths
        expected += weight_value * counts * total_events / total_at_risk
        for a in range(k):
            for b in range(k):
                # 加权和检验方差为 Σ w²·Var：Breslow 权重须平方（log-rank w=1 不变）
                if a == b:
                    variance[a, b] += weight_value**2 * factor * proportion[a] * (1 - proportion[a])
                else:
                    variance[a, b] -= weight_value**2 * factor * proportion[a] * proportion[b]

    difference = (observed - expected)[: k - 1]
    covariance = variance[: k - 1, : k - 1]
    chi2 = float(difference @ np.linalg.pinv(covariance) @ difference)
    df = k - 1
    return {
        "method": weight,
        "chi2": chi2,
        "df": df,
        "p_value": float(sp_stats.chi2.sf(chi2, df)),
        "groups": labels,
        "observed": observed.tolist(),
        "expected": expected.tolist(),
    }

"""统计方法实现（宿主确定性计算）。

每个 handler 接收 (df, step, params)，返回可 JSON 序列化的结果 dict。
策略链：检验方法选择显式记录每步判定依据（strategy.steps[]），最终方法与次优建议可追溯。
方法学依据：项目内《医学统计处理流程图》《顶刊统计策略图谱》的终点类型决策表与决策板。
"""
from __future__ import annotations

import math
import warnings
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from medsta.stats.notes import METHOD_NOTES
from medsta.stats.plotting import cohens_d, summarize_series
from medsta.stats.significance import (
    attach_significance,
    bonferroni_alpha,
    dunn_pvalue,
    lsd_t_pvalue,
    p_adjust,
    scheffe_pvalue,
    significance_label,
    snk_q_pvalue,
    snk_step_down,
    tukey_q_pvalue,
)


def _alpha(params: dict) -> float:
    try:
        return float(params.get("alpha", 0.05))
    except (TypeError, ValueError):
        return 0.05


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(df[column], errors="coerce")


def _groups(df: pd.DataFrame, column: str, group_column: str) -> list[tuple[str, np.ndarray]]:
    groups: list[tuple[str, np.ndarray]] = []
    for key, frame in df.groupby(group_column, sort=False):
        values = _numeric(frame, column).dropna().to_numpy()
        if len(values) > 0:
            groups.append((str(key), values))
    return groups


def _normal_step(groups: list[tuple[str, np.ndarray]]) -> tuple[bool, list[str]]:
    """逐组 Shapiro 正态性；返回 (是否全部正态, 判定记录)。"""
    steps: list[str] = []
    all_normal = True
    for name, values in groups:
        if len(values) < 3:
            steps.append(f"组「{name}」n={len(values)} 过小，正态性检验不可靠，按非正态处理")
            all_normal = False
            continue
        _w, p_value = sp_stats.shapiro(values)
        ok = p_value > 0.05
        steps.append(f"正态性（Shapiro-Wilk）：组「{name}」p={p_value:.4g} → {'正态' if ok else '非正态'}")
        all_normal = all_normal and ok
    return all_normal, steps


def _f_variance_test(
    groups: list[tuple[str, np.ndarray]], alpha: float = 0.10
) -> tuple[bool, list[str], dict]:
    """两独立样本方差齐性 F 检验（教材 §7 公式 7-6，取 α=0.10）。"""
    if len(groups) != 2:
        raise ValueError("F 检验只适用于两组方差比较")
    (_, values_a), (_, values_b) = groups[0], groups[1]
    var_a = float(np.var(values_a, ddof=1))
    var_b = float(np.var(values_b, ddof=1))
    if var_a >= var_b:
        larger, smaller = var_a, var_b
        df1, df2 = len(values_a) - 1, len(values_b) - 1
    else:
        larger, smaller = var_b, var_a
        df1, df2 = len(values_b) - 1, len(values_a) - 1
    if smaller <= 0:
        return True, ["方差齐性（F 检验）：某组方差为 0，无法比较"], {
            "f_value": None,
            "p_value": None,
            "df1": df1,
            "df2": df2,
        }
    f_value = larger / smaller
    cdf = float(sp_stats.f.cdf(f_value, df1, df2))
    p_value = float(2 * min(cdf, 1 - cdf))
    homogeneous = p_value > alpha
    detail = {"f_value": f_value, "p_value": p_value, "df1": df1, "df2": df2}
    steps = [
        f"方差齐性（F 检验）：F={f_value:.4g}, ν1={df1}, ν2={df2}, p={p_value:.4g}"
        f" → {'方差齐' if homogeneous else '方差不齐'}（教材取 α={alpha:.2f}）"
    ]
    return homogeneous, steps, detail


def _levene_step(groups: list[tuple[str, np.ndarray]], alpha: float = 0.10) -> tuple[bool, list[str]]:
    """Levene 方差齐性检验（多组或非正态资料，教材 §8 第五节认可）。"""
    steps: list[str] = []
    samples = [values for _, values in groups]
    statistic, p_value = sp_stats.levene(*samples)
    homogeneous = p_value > alpha
    steps.append(
        f"方差齐性（Levene）：W={statistic:.4g}, p={p_value:.4g} → "
        f"{'方差齐' if homogeneous else '方差不齐'}（α={alpha:.2f}）"
    )
    return homogeneous, steps


def _imbalance_step(groups: list[tuple[str, np.ndarray]]) -> list[str]:
    steps: list[str] = []
    sizes = [len(values) for _, values in groups]
    if sizes and max(sizes) / max(min(sizes), 1) > 2:
        steps.append(
            f"类别不平衡提示：各组样本量 {dict(zip([n for n, _ in groups], sizes))}，"
            "最大/最小超过 2:1，非参数方法或稳健推断更稳妥"
        )
    return steps


def _bootstrap_median_diff(
    a: np.ndarray, b: np.ndarray, *, n_boot: int = 2000, seed: int = 20261023
) -> tuple[float, float]:
    """中位数差的 bootstrap 百分位区间（固定种子，结果可复现）。"""
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot, dtype=float)
    for index in range(n_boot):
        sample_a = rng.choice(a, size=len(a), replace=True)
        sample_b = rng.choice(b, size=len(b), replace=True)
        diffs[index] = np.median(sample_a) - np.median(sample_b)
    low, high = np.percentile(diffs, [2.5, 97.5])
    return float(low), float(high)


def _bootstrap_paired_median_diff(
    a: np.ndarray, b: np.ndarray, *, n_boot: int = 2000, seed: int = 20261023
) -> tuple[float, float]:
    """配对设计中位差区间：对差值做单样本 bootstrap，保留配对结构。"""
    rng = np.random.default_rng(seed)
    pairwise = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    medians = np.median(
        rng.choice(pairwise, size=(n_boot, len(pairwise)), replace=True), axis=1
    )
    low, high = np.percentile(medians, [2.5, 97.5])
    return float(low), float(high)


def describe(df: pd.DataFrame, step: Any, params: dict) -> dict:
    group_by = params.get("group_by")
    stats: dict[str, Any] = {}
    freq_rows: list[dict[str, Any]] = []
    for column in step.target_columns:
        overall = summarize_series(df[column])
        entry: dict[str, Any] = {"overall": overall}
        entry.update({k: v for k, v in overall.items() if k != "n"})
        entry["count"] = overall["n"]
        if group_by:
            entry["groups"] = {
                str(key): summarize_series(frame[column])
                for key, frame in df.groupby(group_by, sort=False)
            }
            entry["group_column"] = group_by
        stats[column] = entry
        if "distinct" in overall:
            # 类别型：频数表（列/取值/频次/占比）
            counts = df[column].dropna().astype(str).value_counts()
            total = int(counts.sum())
            for value, count in counts.items():
                freq_rows.append(
                    {
                        "column": column,
                        "value": value,
                        "count": int(count),
                        "ratio": round(count / total, 4) if total else 0.0,
                    }
                )
    result: dict[str, Any] = {"stats": stats}
    if freq_rows:
        result["table"] = {"columns": ["column", "value", "count", "ratio"], "rows": freq_rows}
    else:
        # 全连续目标：每列一行的汇总统计表（七列口径）
        summary_rows = []
        for column in step.target_columns:
            entry = stats[column]
            summary_rows.append({
                "column": column,
                "count": entry.get("count"),
                "mean": entry.get("mean"),
                "median": entry.get("median"),
                "q25": entry.get("q25"),
                "q75": entry.get("q75"),
                "min": entry.get("min"),
                "max": entry.get("max"),
            })
        result["table"] = {
            "columns": ["column", "count", "mean", "median", "q25", "q75", "min", "max"],
            "rows": summary_rows,
        }
    return result


_MISSING_DISCLAIMER = (
    "缺失机制（MCAR/MAR/MNAR）不能仅凭观测数据断定，必须结合研究设计与未观测信息判断；"
    "下列提示只说明「缺失是否与已观测变量有关」，不构成机制判定。"
)


def _missing_sets(df: pd.DataFrame, columns: list[str]) -> list[frozenset[int]]:
    return [
        frozenset(np.flatnonzero(df[column].isna().to_numpy()).tolist())
        for column in columns
    ]


def _classify_missing_pattern(sets: list[frozenset[int]]) -> str:
    """单变量 / 单调 / 任意（Little & Rubin 的缺失模式分类）。"""
    non_empty = [item for item in sets if item]
    if not non_empty:
        return "none"
    if len(non_empty) == 1:
        return "univariate"
    ordered = sorted(non_empty, key=len)
    if all(ordered[index] <= ordered[index + 1] for index in range(len(ordered) - 1)):
        return "monotonic"
    return "arbitrary"


def _mechanism_hint(
    df: pd.DataFrame, columns: list[str], group_by: str | None
) -> dict[str, Any]:
    """缺失与分组的关联提示；不给机制判定。"""
    if not group_by or group_by not in df.columns:
        return {
            "kind": "inconclusive",
            "detail": "未提供分组变量，无法检验缺失与已观测变量的关系",
            "disclaimer": _MISSING_DISCLAIMER,
        }
    for column in columns:
        mask = df[column].isna()
        if not mask.any() or mask.all():
            continue
        table = pd.crosstab(mask, df[group_by])
        if table.shape[0] != 2 or table.shape[1] < 2:
            continue
        try:
            _chi2, p_value, _dof, _expected = sp_stats.chi2_contingency(
                table, correction=False
            )
        except ValueError:
            continue
        if float(p_value) < 0.05:
            return {
                "kind": "group_related",
                "column": column,
                "group_by": group_by,
                "p_value": float(p_value),
                "detail": (
                    f"列「{column}」的缺失在「{group_by}」各组间差异有统计学意义"
                    f"（P={float(p_value):.4g}），提示缺失可能与分组有关，"
                    "插补模型应纳入该分组变量"
                ),
                "disclaimer": _MISSING_DISCLAIMER,
            }
    return {
        "kind": "inconclusive",
        "detail": "未发现缺失与分组的显著关联；仍不能据此断定 MCAR",
        "disclaimer": _MISSING_DISCLAIMER,
    }


def missing_report(df: pd.DataFrame, step: Any, params: dict) -> dict:
    columns: dict[str, Any] = {}
    total = len(df)
    group_by = params.get("group_by")
    for column in step.target_columns:
        missing = int(df[column].isna().sum())
        entry: dict[str, Any] = {
            "missing": missing,
            "missing_pct": round(missing / total * 100, 2) if total else 0.0,
            "dtype": str(df[column].dtype),
        }
        if group_by:
            entry["by_group"] = {
                str(key): int(frame[column].isna().sum())
                for key, frame in df.groupby(group_by, sort=False)
            }
        columns[column] = entry

    complete_rows = int(df[step.target_columns].dropna().shape[0])
    complete_pct = round(complete_rows / total * 100, 2) if total else 0.0
    sets = _missing_sets(df, list(step.target_columns))
    pattern = _classify_missing_pattern(sets)

    warnings: list[str] = []
    for column in step.target_columns:
        entry = columns[column]
        if entry["missing_pct"] > 50:
            warnings.append(
                f"列「{column}」缺失 {entry['missing_pct']:.1f}%（>50%），建议删除该列而非插补"
            )
    if pattern != "none" and complete_pct < 10:
        warnings.append(
            f"完整病例仅 {complete_rows}/{total}（{complete_pct:.1f}%），"
            "完整病例分析会损失大部分样本，建议插补或改用混合模型"
        )

    return {
        "row_count": total,
        "complete_rows": complete_rows,
        "complete_pct": complete_pct,
        "columns": columns,
        "pattern": pattern,
        "pattern_detail": {
            "missing_counts": {column: len(item) for column, item in zip(step.target_columns, sets)},
            "distinct_patterns": len({item for item in sets if item}),
        },
        "mechanism_hint": _mechanism_hint(df, list(step.target_columns), group_by),
        "warnings": warnings,
        "method_note": METHOD_NOTES["missing_report"],
        "note": "缺失<5% 且疑 MCAR 可完整病例分析；MAR 建议 MICE/MMRM；疑 MNAR 需敏感性分析（见决策板 C）",
    }


def normality_test(df: pd.DataFrame, step: Any, params: dict) -> dict:
    columns: dict[str, Any] = {}
    alpha = _alpha(params)
    for column in step.target_columns:
        values = _numeric(df, column).dropna().to_numpy()
        if len(values) < 3:
            columns[column] = {
                "n": int(len(values)),
                "p_value": None,
                "is_normal": False,
                "note": "样本量不足（n<3），无法做 Shapiro-Wilk 检验",
            }
            continue
        statistic, p_value = sp_stats.shapiro(values)
        columns[column] = {
            "n": int(len(values)),
            "statistic": float(statistic),
            "p_value": float(p_value),
            "is_normal": bool(p_value > alpha),
            "note": "p>α 不拒绝正态假设；n>5000 时检验过于敏感，需结合 Q-Q 图判断",
        }
    return {"method": "shapiro-wilk", "columns": columns}


def levene_test(df: pd.DataFrame, step: Any, params: dict) -> dict:
    column = step.target_columns[0]
    group_column = params["group_column"]
    groups = _groups(df, column, group_column)
    if len(groups) < 2:
        raise ValueError(f"分组列「{group_column}」不足 2 组")
    statistic, p_value = sp_stats.levene(*[values for _, values in groups])
    alpha = _alpha(params)
    result = {
        "column": column,
        "group_column": group_column,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "homogeneous": bool(p_value > alpha),
        "note": "p>α 视为方差齐；不齐时组间比较应使用 Welch 校正或非参数方法",
    }
    return attach_significance(result, "p_value", alpha)


def group_compare(df: pd.DataFrame, step: Any, params: dict) -> dict:
    column = step.target_columns[0]
    group_column = params["group_column"]
    groups = _groups(df, column, group_column)
    if len(groups) < 2:
        raise ValueError(f"分组列「{group_column}」不足 2 组，无法比较")
    (name_a, values_a), (name_b, values_b) = groups[0], groups[1]
    paired = bool(params.get("paired"))
    length = min(len(values_a), len(values_b))
    alpha = _alpha(params)
    strategy_steps: list[str] = []

    if paired:
        # 配对设计：按组内原始行序对齐，任一侧缺失剔除「整对」；
        # 不得对各组分别 dropna 后按行序相减——错位会把不同受试者当配对（P0 修复）
        raw_a = _numeric(df[df[group_column] == name_a], column).reset_index(drop=True)
        raw_b = _numeric(df[df[group_column] == name_b], column).reset_index(drop=True)
        pair_len = min(len(raw_a), len(raw_b))
        arr_a = raw_a.iloc[:pair_len].to_numpy(dtype=float)
        arr_b = raw_b.iloc[:pair_len].to_numpy(dtype=float)
        keep = ~(np.isnan(arr_a) | np.isnan(arr_b))
        values_a = arr_a[keep]
        values_b = arr_b[keep]
        length = int(len(values_a))
        if length < 2:
            raise ValueError(
                f"配对样本剔除任一侧缺失后仅 {length} 对完整配对，至少需要 2 对"
            )
        difference = values_a - values_b
        strategy_steps.append("配对设计：正态性检验针对配对差值，而非两组原始值")
        strategy_steps.append("配对设计不要求两组方差齐性（教材 §7 注意事项 2），跳过方差齐性检验")
        normal, normal_steps = _normal_step([(f"{name_a}−{name_b} 差值", difference)])
        strategy_steps.extend(normal_steps)
        homogeneous = True
    else:
        difference = None
        normal, normal_steps = _normal_step(groups[:2])
        strategy_steps.extend(normal_steps)
        if len(groups) == 2:
            homogeneous, variance_steps, _ = _f_variance_test(groups)
        else:
            homogeneous, variance_steps = _levene_step(groups)
        strategy_steps.extend(variance_steps)
        strategy_steps.extend(_imbalance_step(groups))

    requested = params.get("test", "auto")
    if paired:
        alternatives = {"t": "wilcoxon", "wilcoxon": "t"}
    else:
        alternatives = {"t": "mannwhitney", "welch_t": "mannwhitney", "mannwhitney": "t"}
    if requested != "auto":
        final_method = requested
        strategy_steps.append(f"用户指定检验方法：{requested}（仍建议参考上述判定）")
    elif paired:
        final_method = "t" if normal else "wilcoxon"
        strategy_steps.append(
            "差值近似正态 → 选择配对 t 检验" if normal else "差值非正态 → 选择 Wilcoxon 符号秩检验"
        )
    elif normal and homogeneous:
        final_method = "t"
    elif normal and not homogeneous:
        final_method = "welch_t"
        strategy_steps.append("正态但方差不齐 → 选择 Welch t（不假设等方差）")
    else:
        final_method = "mannwhitney"
        strategy_steps.append("非正态 → 选择 Mann-Whitney U（秩检验）")
    alternative = alternatives.get(final_method, "permutation")

    if final_method == "wilcoxon":
        statistic, p_value = sp_stats.wilcoxon(values_a[:length], values_b[:length])
    elif final_method == "mannwhitney":
        statistic, p_value = sp_stats.mannwhitneyu(values_a, values_b, alternative="two-sided")
    elif paired:
        statistic, p_value = sp_stats.ttest_rel(values_a[:length], values_b[:length])
    elif final_method == "t":
        statistic, p_value = sp_stats.ttest_ind(values_a, values_b, equal_var=True)
    else:  # welch_t
        statistic, p_value = sp_stats.ttest_ind(values_a, values_b, equal_var=False)

    diff = float(values_a.mean() - values_b.mean())
    result: dict[str, Any] = {
        "column": column,
        "group_column": group_column,
        "groups": {name_a: int(len(values_a)), name_b: int(len(values_b))},
        "group_means": {name_a: float(values_a.mean()), name_b: float(values_b.mean())},
        "test": final_method,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "mean_diff": diff,
        "cohens_d": cohens_d(values_a, values_b),
        "strategy": {
            "steps": strategy_steps,
            "final_method": final_method,
            "alternative": f"次优：{alternative}（当检验前提变化时使用）",
        },
        "note": "p 值仅作参考，须同时报告效应量与 95%CI",
    }

    if final_method in ("mannwhitney", "wilcoxon"):
        median_diff = float(np.median(values_a[:length]) - np.median(values_b[:length]))
        if paired:
            low, high = _bootstrap_paired_median_diff(values_a[:length], values_b[:length])
        else:
            low, high = _bootstrap_median_diff(values_a[:length], values_b[:length])
        result.update(
            {
                "ci95": [low, high],
                "ci_method": "bootstrap",
                "ci_target": "median_diff",
                "median_diff": median_diff,
            }
        )
    else:
        if paired:
            se = float(np.std(values_a[:length] - values_b[:length], ddof=1) / math.sqrt(length))
            degrees = float(length - 1)
        elif final_method == "t":
            pooled = (
                (len(values_a) - 1) * np.var(values_a, ddof=1)
                + (len(values_b) - 1) * np.var(values_b, ddof=1)
            ) / (len(values_a) + len(values_b) - 2)
            se = float(math.sqrt(pooled) * math.sqrt(1 / len(values_a) + 1 / len(values_b)))
            degrees = float(len(values_a) + len(values_b) - 2)
        else:  # welch_t
            var_a = np.var(values_a, ddof=1) / len(values_a)
            var_b = np.var(values_b, ddof=1) / len(values_b)
            se = float(math.sqrt(var_a + var_b))
            degrees = float(
                (var_a + var_b) ** 2
                / (var_a**2 / (len(values_a) - 1) + var_b**2 / (len(values_b) - 1))
            )
        t_critical = float(sp_stats.t.ppf(1 - alpha / 2, degrees))
        result.update(
            {
                "ci95": [diff - t_critical * se, diff + t_critical * se],
                "ci_method": "t",
                "ci_target": "mean_diff",
                "df": degrees,
                "t_critical": t_critical,
                "se": float(se),
            }
        )

    attach_significance(result, "p_value", alpha)
    result["table"] = {
        "columns": ["test", "statistic", "p_value", "significance"],
        "rows": [
            {
                "test": final_method,
                "statistic": float(statistic),
                "p_value": float(p_value),
                "significance": result["stars"],
            }
        ],
    }
    return result


def _snk_rows(
    groups: list[tuple[str, np.ndarray]], ms_error: float, df_error: int, alpha: float
) -> list[dict[str, Any]]:
    """SNK-q 两两比较（教材 §8-4 公式 8-9）。"""
    entries = [(name, float(values.mean()), len(values)) for name, values in groups]
    ranked = sorted(entries, key=lambda item: item[1], reverse=True)
    position = {name: index for index, (name, _, _) in enumerate(ranked)}
    rows: list[dict[str, Any]] = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            name_a, mean_a, n_a = entries[i]
            name_b, mean_b, n_b = entries[j]
            span = abs(position[name_a] - position[name_b]) + 1
            q_value, p_value = snk_q_pvalue(mean_a, mean_b, n_a, n_b, ms_error, df_error, span)
            rows.append(
                {
                    "group_a": name_a,
                    "group_b": name_b,
                    "mean_diff": round(mean_a - mean_b, 4),
                    "q_value": round(q_value, 4),
                    "span": span,
                    "p_value": p_value,
                    "adjusted_p": p_value,
                    "statistic": round(q_value, 4),
                    "method": "snk",
                }
            )
    return rows


def _pair_entries(
    groups: list[tuple[str, np.ndarray]],
) -> list[tuple[str, float, int, str, float, int]]:
    entries: list[tuple[str, float, int, str, float, int]] = []
    for i in range(len(groups)):
        name_a, values_a = groups[i]
        mean_a, n_a = float(values_a.mean()), len(values_a)
        for j in range(i + 1, len(groups)):
            name_b, values_b = groups[j]
            entries.append((name_a, mean_a, n_a, name_b, float(values_b.mean()), len(values_b)))
    return entries


def _tukey_rows(
    groups: list[tuple[str, np.ndarray]], ms_error: float, df_error: int, alpha: float
) -> list[dict[str, Any]]:
    """Tukey HSD（Tukey-Kramer）：studentized range 的组数固定为 k。"""
    method = "tukey"
    rows: list[dict[str, Any]] = []
    for name_a, mean_a, n_a, name_b, mean_b, n_b in _pair_entries(groups):
        q_value, p_value = tukey_q_pvalue(
            mean_a, mean_b, n_a, n_b, ms_error, df_error, len(groups)
        )
        rows.append(
            {
                "group_a": name_a,
                "group_b": name_b,
                "mean_diff": round(mean_a - mean_b, 4),
                "q_value": round(q_value, 4),
                "p_value": p_value,
                "adjusted_p": p_value,
                "statistic": round(q_value, 4),
                "method": method,
            }
        )
    return rows


def _lsd_rows(
    groups: list[tuple[str, np.ndarray]], ms_error: float, df_error: int, alpha: float
) -> list[dict[str, Any]]:
    """LSD-t：成对合并方差 t，不做多重性校正。"""
    method = "lsd"
    rows: list[dict[str, Any]] = []
    for name_a, mean_a, n_a, name_b, mean_b, n_b in _pair_entries(groups):
        t_value, p_value = lsd_t_pvalue(mean_a, mean_b, n_a, n_b, ms_error, df_error)
        rows.append(
            {
                "group_a": name_a,
                "group_b": name_b,
                "mean_diff": round(mean_a - mean_b, 4),
                "p_value": p_value,
                "adjusted_p": p_value,
                "statistic": round(t_value, 4),
                "method": method,
            }
        )
    return rows


def _scheffe_rows(
    groups: list[tuple[str, np.ndarray]], ms_error: float, df_error: int, alpha: float
) -> list[dict[str, Any]]:
    """Scheffé 两两比较：控制全族误差率，比 Tukey 保守。"""
    method = "scheffe"
    rows: list[dict[str, Any]] = []
    for name_a, mean_a, n_a, name_b, mean_b, n_b in _pair_entries(groups):
        f_value, p_value = scheffe_pvalue(
            mean_a, mean_b, n_a, n_b, ms_error, df_error, len(groups)
        )
        rows.append(
            {
                "group_a": name_a,
                "group_b": name_b,
                "mean_diff": round(mean_a - mean_b, 4),
                "f_value": round(f_value, 4),
                "p_value": p_value,
                "adjusted_p": p_value,
                "statistic": round(f_value, 4),
                "method": method,
            }
        )
    return rows


def _dunnett_rows(
    groups: list[tuple[str, np.ndarray]],
    ms_error: float,
    df_error: int,
    alpha: float,
    control_group: Any,
) -> list[dict[str, Any]]:
    """Dunnett：多个试验组对同一对照，p 值来自多元 t 分布（scipy.stats.dunnett）。"""
    labels = [name for name, _ in groups]
    if not control_group:
        raise ValueError(
            f"Dunnett 需要指定 control_group（对照组）；可选组：{', '.join(labels)}"
        )
    if str(control_group) not in labels:
        raise ValueError(
            f"对照组「{control_group}」不存在；可选组：{', '.join(labels)}"
        )

    control_values = dict(groups)[str(control_group)]
    experimental = [(name, values) for name, values in groups if name != str(control_group)]
    if not experimental:
        raise ValueError("Dunnett 至少需要一个试验组与对照组比较")

    # scipy 的 dunnett 用数值积分/模拟，必须固定随机源才能复现
    outcome = sp_stats.dunnett(
        *[values for _, values in experimental],
        control=control_values,
        alternative="two-sided",
        random_state=np.random.default_rng(20261023),
    )
    control_mean = float(control_values.mean())
    rows: list[dict[str, Any]] = []
    for (name, values), statistic, p_value in zip(
        experimental, outcome.statistic, outcome.pvalue
    ):
        rows.append(
            {
                "group_a": str(control_group),
                "group_b": name,
                "mean_diff": round(float(values.mean()) - control_mean, 4),
                "p_value": float(p_value),
                "adjusted_p": float(p_value),
                "statistic": round(float(statistic), 4),
                "method": "dunnett",
            }
        )
    return rows


def _dunn_rows(groups: list[tuple[str, np.ndarray]]) -> list[dict[str, Any]]:
    """Kruskal-Wallis 之后的 Dunn 事后比较（教材未给公式，采用通用做法）。"""
    all_values = np.concatenate([values for _, values in groups])
    total_n = len(all_values)
    ranks = sp_stats.rankdata(all_values)
    rank_means: dict[str, float] = {}
    cursor = 0
    for name, values in groups:
        segment = ranks[cursor : cursor + len(values)]
        rank_means[name] = float(segment.mean())
        cursor += len(values)

    _, counts = np.unique(all_values, return_counts=True)
    ties = 1.0
    if total_n > 1:
        ties = 1 - float(((counts**3 - counts).sum()) / (total_n**3 - total_n))

    rows: list[dict[str, Any]] = []
    for i in range(len(groups)):
        name_a, values_a = groups[i]
        for j in range(i + 1, len(groups)):
            name_b, values_b = groups[j]
            z_value, p_value = dunn_pvalue(
                rank_means[name_a],
                rank_means[name_b],
                len(values_a),
                len(values_b),
                total_n,
                ties,
            )
            rows.append(
                {
                    "group_a": name_a,
                    "group_b": name_b,
                    "z_value": round(z_value, 4),
                    "p_value": p_value,
                    "statistic": round(z_value, 4),
                    "method": "dunn",
                }
            )
    return rows


def anova(df: pd.DataFrame, step: Any, params: dict) -> dict:
    column = step.target_columns[0]
    group_column = params["group_column"]
    groups = _groups(df, column, group_column)
    if len(groups) < 2:
        raise ValueError(f"分组列「{group_column}」不足 2 组，无法做组间比较")
    samples = [values for _, values in groups]
    strategy_steps: list[str] = []
    normal, normal_steps = _normal_step(groups)
    strategy_steps.extend(normal_steps)
    homogeneous, levene_steps = _levene_step(groups)
    strategy_steps.extend(levene_steps)
    strategy_steps.extend(_imbalance_step(groups))

    requested = params.get("test", "auto")
    test = requested
    if requested == "auto":
        test = "anova" if normal else "kruskal"
        strategy_steps.append(f"→ 选择 {test}（依据上述正态性判定）")
    alternatives = {"anova": "kruskal", "kruskal": "anova", "welch_anova": "kruskal"}

    if test == "anova":
        statistic, p_value = sp_stats.f_oneway(*samples)
        all_values = np.concatenate(samples)
        grand = all_values.mean()
        ss_between = sum(len(v) * (v.mean() - grand) ** 2 for v in samples)
        ss_total = float(((all_values - grand) ** 2).sum())
        effect = {"eta_squared": ss_between / ss_total if ss_total else 0.0}
        if not homogeneous:
            strategy_steps.append("方差不齐：ANOVA 结论需谨慎，可改用 Welch ANOVA 或 Kruskal-Wallis")
    else:
        statistic, p_value = sp_stats.kruskal(*samples)
        n = sum(len(v) for v in samples)
        effect = {"epsilon_squared": float(statistic) / (n - 1) if n > 1 else 0.0}
    alpha = _alpha(params)
    result: dict[str, Any] = {
        "column": column,
        "group_column": group_column,
        "groups": {name: int(len(values)) for name, values in groups},
        "test": test,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "overall": {"statistic": float(statistic), "p_value": float(p_value), **effect},
        **effect,
        "strategy": {
            "steps": strategy_steps,
            "final_method": test,
            "alternative": f"次优：{alternatives.get(test, 'permutation')}",
        },
        "note": "p 值仅作参考，须同时报告效应量",
        "method_note": METHOD_NOTES["anova"],
    }
    attach_significance(result, "p_value", alpha)

    if len(groups) >= 3:
        correction = str(params.get("correction", "snk") or "snk")
        parametric = {"snk", "tukey", "dunnett", "lsd", "scheffe"}
        if test == "anova" and correction in parametric:
            all_values = np.concatenate(samples)
            grand_value = float(all_values.mean())
            ss_total_value = float(((all_values - grand_value) ** 2).sum())
            ss_between = sum(len(values) * (values.mean() - grand_value) ** 2 for values in samples)
            df_within = len(all_values) - len(groups)
            ms_within = (ss_total_value - ss_between) / df_within

            if correction == "snk":
                rows = snk_step_down(_snk_rows(groups, ms_within, df_within, alpha), alpha)
                warning = (
                    "多重检验提醒：多组两两比较已按 SNK-q 法（教材 §8-4）逐步判定；"
                    "跨度最大的比较不显著时更小跨度不再判为显著，显著性以 significant 字段为准"
                )
            elif correction == "tukey":
                rows = _tukey_rows(groups, ms_within, df_within, alpha)
                warning = (
                    "多重检验提醒：已按 Tukey HSD（Tukey-Kramer，studentized range 组数固定为 k）"
                    "做全族比较并控制 EER；不等样本量时即 Tukey-Kramer 近似"
                )
            elif correction == "dunnett":
                rows = _dunnett_rows(
                    groups, ms_within, df_within, alpha, params.get("control_group")
                )
                warning = (
                    "多重检验提醒：已按 Dunnett 检验只比较「对照组 vs 各试验组」并控制 FWER；"
                    "组间两两比较未做，若需要全部两两比较请改用 Tukey 或 SNK"
                )
            elif correction == "lsd":
                rows = _lsd_rows(groups, ms_within, df_within, alpha)
                warning = (
                    "多重检验提醒：LSD-t 不做多重性校正，只适合分析前已设定的少数对比；"
                    "用它对全部组合作探索性两两比较会膨胀 I 类错误，建议改用 Tukey 或 SNK"
                )
            else:
                rows = _scheffe_rows(groups, ms_within, df_within, alpha)
                warning = (
                    "多重检验提醒：已按 Scheffé 法做全族比较（控制 FWER，比 Tukey 更保守）；"
                    "结论偏保守，样本量较小时可能检不出真实差异"
                )

            if correction == "snk":
                # SNK 的 significant 由逐步规则决定，这里只补星号，不能覆盖
                for row in rows:
                    row["stars"] = significance_label(row["p_value"], alpha)["stars"]
            else:
                for row in rows:
                    row.update(significance_label(row["p_value"], alpha))
            method_used = correction
        elif test == "anova":
            rows = _mean_diff_rows(groups)
            adjusted = p_adjust([float(row["p_value"]) for row in rows], correction)
            for row, adj_p in zip(rows, adjusted):
                row["adjusted_p"] = adj_p
                row["method"] = correction
                row.update(significance_label(adj_p, alpha))
            method_used = correction
            warning = (
                f"多重检验提醒：多组两两比较未经校正会膨胀 I 类错误，已按 {correction} 做多重性校正；"
                "显著性判断以校正后 p 值（adjusted_p）为准"
            )
        else:
            rows = _dunn_rows(groups)
            adjusted = p_adjust([float(row["p_value"]) for row in rows], "bonferroni")
            for row, adj_p in zip(rows, adjusted):
                row["adjusted_p"] = adj_p
                row.update(significance_label(adj_p, alpha))
            method_used = "dunn"
            if correction in parametric:
                warning = (
                    f"多重检验提醒：数据判为非正态（Kruskal-Wallis），已忽略 correction={correction} "
                    "的参数事后方法（避免使用错误的误差均方），改用 Dunn + Bonferroni；"
                    "教材 §10 未给该事后公式，此处采用通用做法"
                )
            else:
                warning = (
                    "多重检验提醒：Kruskal-Wallis 显著后按 Dunn 法做两两比较并做 Bonferroni 校正；"
                    "教材 §10 未给出该事后公式，此处采用通用做法，显著性以 adjusted_p 为准"
                )
        result["pairwise"] = {
            "method": method_used,
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
        }
        result["table"] = result["pairwise"]
        result["multiplicity_warning"] = warning
    return result


def _mean_diff_rows(groups: list[tuple[str, np.ndarray]]) -> list[dict[str, Any]]:
    """双侧 Welch t 的均值差两两比较（供 Holm/Bonferroni 校正路径使用）。"""
    rows: list[dict[str, Any]] = []
    for i in range(len(groups)):
        name_i, values_i = groups[i]
        for j in range(i + 1, len(groups)):
            name_j, values_j = groups[j]
            statistic, p_value = sp_stats.ttest_ind(values_i, values_j, equal_var=False)
            rows.append(
                {
                    "group_a": name_i,
                    "group_b": name_j,
                    "mean_diff": round(float(values_i.mean() - values_j.mean()), 4),
                    "statistic": float(statistic),
                    "p_value": float(p_value),
                }
            )
    return rows


def chi_square(df: pd.DataFrame, step: Any, params: dict) -> dict:
    if len(step.target_columns) >= 2:
        row_column, col_column = step.target_columns[0], step.target_columns[1]
    else:
        row_column = params["row_column"]
        col_column = params["col_column"]
    table = pd.crosstab(df[row_column], df[col_column])
    if table.shape[0] < 2 or table.shape[1] < 2:
        raise ValueError("列联表需至少 2×2 才能做卡方检验")

    n = int(table.to_numpy().sum())
    expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / n
    min_expected = float(expected.min())
    low_cells = int((expected < 5).sum())
    low_ratio = low_cells / expected.size
    strategy_steps = [
        f"数据量分析：总样本 n={n}，最小期望频数={min_expected:.2f}，"
        f"期望<5 的格子 {low_cells}/{expected.size}（{low_ratio:.0%}）",
    ]
    category_counts = df[row_column].value_counts()
    rare = category_counts[category_counts < 5]
    if len(rare):
        strategy_steps.append(
            f"类别不平衡提示：{dict(rare)} 样本过少（n<5），建议合并类别或补充样本"
        )

    is_2x2 = table.shape == (2, 2)
    alpha = _alpha(params)
    mode = params.get("correction", "auto")
    if isinstance(mode, bool):
        mode = "yes" if mode else "no"
    mode = str(mode or "auto")
    result: dict[str, Any] = {
        "row_column": row_column,
        "col_column": col_column,
        "table": table.to_dict(),
    }

    if is_2x2:
        if mode == "auto":
            if n >= 40 and min_expected >= 5:
                tier = "pearson"
            elif n >= 40 and min_expected >= 1:
                tier = "corrected"
            else:
                tier = "fisher"
        elif mode == "yes":
            tier = "corrected"
        elif mode == "no":
            tier = "pearson"
        else:
            raise ValueError(f"未知校正设定：{mode}（可选 auto/yes/no）")

        if tier == "fisher":
            odds_ratio, p_value = sp_stats.fisher_exact(table)
            result.update({"p_value": float(p_value), "odds_ratio": float(odds_ratio)})
            strategy_steps.append(
                f"2×2 表 n={n}、最小期望={min_expected:.2f} 不满足卡方条件（n<40 或 T<1）"
                " → 采用 Fisher 精确检验"
            )
            final_method = "fisher_exact"
            alternative = "次优：增大样本量使期望频数满足卡方条件后改用卡方检验"
        else:
            correction_flag = tier == "corrected"
            chi2, p_value, dof, _ = sp_stats.chi2_contingency(
                table, correction=correction_flag
            )
            result.update(
                {"chi2": float(chi2), "dof": int(dof), "p_value": float(p_value)}
            )
            label = "校正公式" if correction_flag else "专用公式"
            strategy_steps.append(
                f"2×2 表 n={n}、最小期望={min_expected:.2f} → 采用{label}（教材 §9-1）"
            )
            final_method = "chi_square"
            alternative = "次优：Fisher 精确检验（当期望频数条件不满足时）"
        result["tier"] = tier
        result["corrected"] = tier == "corrected"
    else:
        if low_ratio > 0.2 or min_expected < 1:
            raise ValueError(
                f"R×C 表期望频数不足（最小期望 {min_expected:.2f}，期望<5 占 {low_ratio:.0%}）："
                "建议增大样本量，或将相邻类别合并后重新检验"
            )
        chi2, p_value, dof, _ = sp_stats.chi2_contingency(table, correction=False)
        result.update({"chi2": float(chi2), "dof": int(dof), "p_value": float(p_value)})
        result["tier"] = "rxc"
        result["corrected"] = False
        final_method = "chi_square"
        alternative = "次优：Fisher 精确检验（仅适用于 2×2）"

    # 先附加显著性星号，保证内嵌表的 significance 与最终判定一致
    attach_significance(result, "p_value", alpha)

    result["strategy"] = {
        "steps": strategy_steps,
        "final_method": final_method,
        "alternative": alternative,
    }

    chi2_for_v = result.get("chi2")
    if chi2_for_v is None:
        # Fisher 精确路径无 χ² 统计量：按观测表补算近似 χ² 供效应量参考
        chi2_for_v = float(sp_stats.chi2_contingency(table, correction=False)[0])
        result["effect_chi2"] = chi2_for_v
    result["cramers_v"] = (
        float(np.sqrt(chi2_for_v / (n * (min(table.shape) - 1)))) if n else 0.0
    )
    count_rows = [
        {row_column: str(row_name), **{str(col): int(table.loc[row_name, col]) for col in table.columns}}
        for row_name in table.index
    ]
    result["table"] = {
        "columns": [row_column, *[str(col) for col in table.columns]],
        "rows": count_rows,
        "stats": [
            {
                "metric": result["strategy"]["final_method"],
                "p_value": result.get("p_value"),
                "significance": result.get("stars", "ns"),
            }
        ],
    }
    result["strategy"]["steps"] = strategy_steps
    result["note"] = (
        "2×2 表按教材三档判定（n≥40 且 T≥5 用专用公式、n≥40 且 1≤T<5 用校正、n<40 或 T<1 用 Fisher）；"
        "R×C 表要求期望<5 的格子不超过 20% 且最小期望≥1"
    )
    event_value = params.get("event_value")
    result["group_rates"] = _group_rates(table, event_value)
    if not is_2x2 and table.shape[1] == 2 and float(result.get("p_value", 1.0)) < alpha:
        comparison = str(params.get("comparison", "all_pairs") or "all_pairs")
        result["pairwise"] = _rate_pairwise(table, alpha, comparison)
    result["method_note"] = METHOD_NOTES["chi_square"]
    return result


def _group_rates(table: pd.DataFrame, event_value: Any = None) -> list[dict[str, Any]]:
    """每行的率与 95%CI：n≥40 用 Wald 正态近似，n<40 用 Wilson 区间。

    `event_value` 指定率分子的取值；未指定时取列联表第一列，并在输出 `rate_column` 标注，
    避免「有效率/无效率」因列顺序不同而产生歧义。
    """
    if event_value is not None and str(event_value) not in {str(item) for item in table.columns}:
        raise ValueError(
            f"event_value「{event_value}」不在列联表列中：{', '.join(map(str, table.columns))}"
        )
    if event_value is not None:
        rate_column = str(event_value)
        event_counts = table[str(event_value)] if str(event_value) in table.columns else table[event_value]
    else:
        rate_column = str(table.columns[0])
        event_counts = table.iloc[:, 0]

    rows: list[dict[str, Any]] = []
    for (group, row), events in zip(table.iterrows(), event_counts):
        total = int(row.sum())
        events = int(events)
        rate = events / total if total else 0.0
        if total >= 40:
            standard_error = math.sqrt(rate * (1 - rate) / total)
            low = rate - 1.96 * standard_error
            high = rate + 1.96 * standard_error
            method = "wald"
        else:
            z_value = 1.96
            denominator = 1 + z_value**2 / total
            centre = (rate + z_value**2 / (2 * total)) / denominator
            half = (
                z_value
                * math.sqrt(rate * (1 - rate) / total + z_value**2 / (4 * total * total))
                / denominator
            )
            low, high = centre - half, centre + half
            method = "wilson"
        rows.append(
            {
                "group": str(group),
                "rate_column": rate_column,
                "n": total,
                "events": events,
                "rate": round(rate, 6),
                "ci_low": round(max(low, 0.0), 6),
                "ci_high": round(min(high, 1.0), 6),
                "ci_method": method,
            }
        )
    return rows


def _rate_pairwise(table: pd.DataFrame, alpha: float, comparison: str) -> dict:
    """多个样本率两两比较：χ² 分割法 + Bonferroni 调整水准（教材 §9-3 二）。"""
    labels = list(table.index)
    if comparison == "vs_control":
        control = labels[0]
        pairs = [(control, other) for other in labels[1:]]
    else:
        comparison = "all_pairs"
        pairs = list(combinations(labels, 2))

    divisor = max(len(pairs), 1)
    alpha_prime = bonferroni_alpha(alpha, divisor)
    rows: list[dict[str, Any]] = []
    for first, second in pairs:
        subset = table.loc[[first, second]]
        chi2, p_value, _dof, _ = sp_stats.chi2_contingency(subset, correction=False)
        adjusted = min(float(p_value) * divisor, 1.0)
        rows.append(
            {
                "group_a": str(first),
                "group_b": str(second),
                "chi2": round(float(chi2), 4),
                "p_value": float(p_value),
                "adjusted_p": adjusted,
                **significance_label(adjusted, alpha),
            }
        )
    return {
        "method": "chi_square_partition",
        "comparison": comparison,
        "alpha_prime": alpha_prime,
        "columns": list(rows[0].keys()) if rows else [],
        "rows": rows,
    }


_CAUSALITY_NOTE = (
    "相关有统计学意义不等于因果关系；因果推断需依靠研究设计与专业知识"
    "（教材 §11 注意事项 3）。"
)


def _strength_label(r: float) -> str:
    """相关强度分档（教材 §11 注意事项 2）。"""
    magnitude = abs(float(r))
    if magnitude <= 0.3:
        return "较差"
    if magnitude <= 0.6:
        return "中度"
    if magnitude <= 0.8:
        return "较高"
    return "很高"


def correlation(df: pd.DataFrame, step: Any, params: dict) -> dict:
    method = params.get("method", "pearson")
    columns = list(step.target_columns)
    numeric = df[columns].apply(pd.to_numeric, errors="coerce")
    matrix = numeric.corr(method=method)
    pairs: dict[str, Any] = {}
    alpha = _alpha(params)
    for i, first in enumerate(columns):
        for second in columns[i + 1:]:
            frame = numeric[[first, second]].dropna()
            if len(frame) < 3:
                continue
            if method == "spearman":
                r, p_value = sp_stats.spearmanr(frame[first], frame[second])
            elif method == "kendall":
                r, p_value = sp_stats.kendalltau(frame[first], frame[second])
            else:
                r, p_value = sp_stats.pearsonr(frame[first], frame[second])
            pairs[f"{first}_{second}"] = {
                "r": float(r),
                "r_squared": round(float(r) ** 2, 4),
                "strength": _strength_label(r),
                "p_value": float(p_value),
                "n": int(len(frame)),
            }
            pairs[f"{first}_{second}"].update(significance_label(p_value, alpha))
    rounded = matrix.round(4).to_dict()
    pair_rows = [
        {
            "pair": key,
            **{
                k: value
                for k, value in stat.items()
                if k in ("r", "r_squared", "strength", "p_value", "stars")
            },
        }
        for key, stat in pairs.items()
    ]
    return {
        "method": method,
        "matrix": rounded,
        "correlation": rounded,  # 兼容旧契约
        "pairs": pairs,
        "table": {
            "columns": ["pair", "r", "r_squared", "strength", "p_value", "significance"],
            "rows": pair_rows,
        },
        "causality_note": _CAUSALITY_NOTE,
        "method_note": METHOD_NOTES["correlation"],
    }


def _regression_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """回归数值表：类别列在这里点名拒绝，避免 coerce 成全缺失后再在拟合时崩。"""
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"回归列不存在：{', '.join(missing)}")
    converted = df[list(columns)].apply(pd.to_numeric, errors="coerce")
    bad: list[str] = []
    for column in columns:
        introduced = int((converted[column].isna() & df[column].notna()).sum())
        if introduced:
            bad.append(f"「{column}」含 {introduced} 个非数值")
    if bad:
        raise ValueError(
            "回归的结局和自变量必须是数值："
            + "；".join(bad)
            + "。类别列请先编码为数值，或改用分类方法"
        )
    frame = converted.dropna()
    if frame.empty:
        raise ValueError("回归有效样本为 0：结局或自变量在对齐后没有完整数值行")
    return frame


def regression(df: pd.DataFrame, step: Any, params: dict) -> dict:
    import statsmodels.api as sm

    target = params["target"]
    features = list(params["features"])
    frame = _regression_frame(df, [target, *features])
    y = frame[target].astype(float)
    x = sm.add_constant(frame[features].astype(float))
    model = sm.OLS(y, x).fit()
    ci = model.conf_int()
    alpha = _alpha(params)
    coefficients = {}
    for name in model.params.index:
        entry = {
            "estimate": float(model.params[name]),
            "ci_low": float(ci.loc[name, 0]),
            "ci_high": float(ci.loc[name, 1]),
            "p_value": float(model.pvalues[name]),
        }
        coefficients[name] = {**entry, **significance_label(entry["p_value"], alpha)}
    coef_rows = [
        {"term": name, **{k: v for k, v in stat.items() if k in ("estimate", "p_value", "stars")}}
        for name, stat in coefficients.items()
    ]
    residuals = np.asarray(model.resid, dtype=float)
    shapiro_p = float(sp_stats.shapiro(residuals).pvalue) if len(residuals) > 2 else None
    try:
        from statsmodels.stats.diagnostic import het_breuschpagan

        _bp_stat, bp_p, _bp_f, _bp_fp = het_breuschpagan(residuals, x)
        breusch_pagan_p = float(bp_p)
    except Exception:
        breusch_pagan_p = None

    feature_count = len(features)
    per_feature = float(model.nobs) / feature_count if feature_count else None
    diagnostic_notes: list[str] = []
    if shapiro_p is not None:
        diagnostic_notes.append(f"残差正态性 Shapiro P={shapiro_p:.3f}")
    if breusch_pagan_p is not None:
        diagnostic_notes.append(f"等方差 Breusch-Pagan P={breusch_pagan_p:.3f}")
    if per_feature is not None and per_feature < 10:
        diagnostic_notes.append(
            f"样本量与特征数之比 {per_feature:.1f}:1 低于 10:1，存在过拟合风险"
        )

    return {
        "target": target,
        "features": features,
        "n": int(model.nobs),
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "f_pvalue": float(model.f_pvalue),
        "alpha": alpha,
        "coefficients": coefficients,
        "anova_table": {
            "ss_total": float(model.centered_tss),
            "ss_regression": float(model.ess),
            "ss_residual": float(model.ssr),
            "df_regression": int(model.df_model),
            "df_residual": int(model.df_resid),
            "ms_regression": float(model.ess / model.df_model) if model.df_model else None,
            "ms_residual": float(model.ssr / model.df_resid) if model.df_resid else None,
            "f_value": float(model.fvalue) if model.fvalue == model.fvalue else None,
            "f_pvalue": float(model.f_pvalue),
        },
        "diagnostics": {
            "residual_shapiro_p": shapiro_p,
            "breusch_pagan_p": breusch_pagan_p,
            "n_per_feature": per_feature,
            "note": "；".join(diagnostic_notes),
        },
        "table": {"columns": ["term", "estimate", "p_value", "significance"], "rows": coef_rows},
        "note": "线性回归假设：线性、独立、同方差、残差正态；违反时考虑稳健标准误或变换",
        "method_note": METHOD_NOTES["regression"],
    }


def logistic_regression(df: pd.DataFrame, step: Any, params: dict) -> dict:
    import statsmodels.api as sm

    target = params["target"]
    features = list(params["features"])
    frame = _regression_frame(df, [target, *features])
    y = frame[target].astype(float)
    if not set(y.unique().tolist()) <= {0.0, 1.0}:
        raise ValueError(f"logistic 回归结局「{target}」必须为 0/1 二分类")
    x = sm.add_constant(frame[features].astype(float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = sm.Logit(y, x).fit(disp=False)
    ci = model.conf_int()

    # 分离检测：完美/准完美预测会让 MLE 发散，OR 与 CI 不再可估计。
    # 三重条件（未收敛 / |β| 过大 / OR 非有限）避免把溢出数值当结果下发。
    params_array = model.params.to_numpy(dtype=float)
    ci_array = ci.to_numpy(dtype=float)
    converged = bool((model.mle_retvals or {}).get("converged", True))
    max_abs_beta = float(np.max(np.abs(params_array))) if params_array.size else 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        odds_finite = bool(
            np.isfinite(np.exp(params_array)).all() and np.isfinite(np.exp(ci_array)).all()
        )
    if not converged or max_abs_beta >= 15.0 or not odds_finite:
        raise ValueError(
            f"logistic 回归无法估计：结局「{target}」与协变量存在完全/准完全分离"
            f"（max|β|={max_abs_beta:.1f}，converged={converged}），OR 不可估计。"
            "建议减少协变量或合并稀疏类别、增大样本；或改用 Firth 惩罚回归。"
        )

    alpha = _alpha(params)
    odds_ratios = {}
    for name in model.params.index:
        entry = {
            "odds_ratio": float(np.exp(model.params[name])),
            "ci_low": float(np.exp(ci.loc[name, 0])),
            "ci_high": float(np.exp(ci.loc[name, 1])),
            "p_value": float(model.pvalues[name]),
        }
        odds_ratios[name] = {**entry, **significance_label(entry["p_value"], alpha)}
    predicted = (model.predict(x) >= 0.5).astype(int)
    auc = _auc(model.predict(x).to_numpy(), y.to_numpy())
    return {
        "target": target,
        "features": features,
        "n": int(model.nobs),
        "pseudo_r_squared": float(model.prsquared),
        "odds_ratios": odds_ratios,
        "accuracy": float((predicted == y.astype(int)).mean()),
        "auc": auc,
        "event_rate": float((y == 1).mean()),
        "alpha": alpha,
        "note": "OR>1 表示该因素与结局发生风险正相关；须结合 95%CI 与临床意义解读",
    }


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    labels = np.asarray(labels).astype(int)
    # 平均秩（Mann-Whitney 并列修正）：并列预测值之间各计 0.5
    ranks = sp_stats.rankdata(scores)
    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    rank_sum_pos = ranks[labels == 1].sum()
    return float((rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def timeseries_forecast(df: pd.DataFrame, step: Any, params: dict) -> dict:
    column = step.target_columns[0]
    horizon = int(params.get("forecast_n", 5))
    series = _numeric(df, column).dropna().to_numpy()
    if len(series) < 3:
        raise ValueError(f"列「{column}」有效点不足 3 个，无法做趋势预测")
    x = np.arange(len(series))
    slope, intercept = np.polyfit(x, series, 1)
    fitted = slope * x + intercept
    ss_res = float(((series - fitted) ** 2).sum())
    ss_tot = float(((series - series.mean()) ** 2).sum())
    future_x = np.arange(len(series), len(series) + horizon)
    forecast = slope * future_x + intercept
    step.params["_forecast_values"] = [float(v) for v in forecast]
    return {
        "column": column,
        "model": "linear_trend",
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": 1 - ss_res / ss_tot if ss_tot else 0.0,
        "forecast_n": horizon,
        "forecast_values": [float(v) for v in forecast],
        "note": "线性趋势仅适用于短期平稳序列；存在季节性/自相关时应改用 ARIMA/状态空间模型",
    }


def aggregate_table(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """group_col × value_col × agg 汇总表：交付为可视化表格。"""
    group_column = params["group_column"]
    agg = params.get("agg", "mean")
    allowed = {"mean", "median", "count", "sum", "std", "min", "max"}
    if agg not in allowed:
        raise ValueError(f"不支持的聚合方式：{agg}（可选 {sorted(allowed)}）")
    rows: list[dict[str, Any]] = []
    for key, frame in df.groupby(group_column, sort=False):
        row: dict[str, Any] = {"group": str(key), "n": int(len(frame))}
        for column in step.target_columns:
            values = _numeric(frame, column).dropna()
            row[column] = float(values.agg(agg)) if len(values) else None
        rows.append(row)
    columns = ["group", "n", *step.target_columns]
    return {
        "group_column": group_column,
        "agg": agg,
        "table": {"columns": columns, "rows": rows},
        "note": f"按「{group_column}」分组对 {step.target_columns} 做 {agg} 聚合",
    }

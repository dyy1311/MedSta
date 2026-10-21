"""统计方法实现（宿主确定性计算）。

每个 handler 接收 (df, step, params)，返回可 JSON 序列化的结果 dict。
策略链：检验方法选择显式记录每步判定依据（strategy.steps[]），最终方法与次优建议可追溯。
方法学依据：项目内《医学统计处理流程图》《顶刊统计策略图谱》的终点类型决策表与决策板。
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from medsta.stats.plotting import cohens_d, summarize_series
from medsta.stats.significance import attach_significance, p_adjust, significance_label


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


def _levene_step(groups: list[tuple[str, np.ndarray]]) -> tuple[bool, list[str]]:
    """Levene 方差齐性检验。"""
    steps: list[str] = []
    samples = [values for _, values in groups]
    statistic, p_value = sp_stats.levene(*samples)
    homogeneous = p_value > 0.05
    steps.append(
        f"方差齐性（Levene）：W={statistic:.4g}, p={p_value:.4g} → {'方差齐' if homogeneous else '方差不齐'}"
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


def missing_report(df: pd.DataFrame, step: Any, params: dict) -> dict:
    columns: dict[str, Any] = {}
    total = len(df)
    for column in step.target_columns:
        missing = int(df[column].isna().sum())
        entry: dict[str, Any] = {
            "missing": missing,
            "missing_pct": round(missing / total * 100, 2) if total else 0.0,
            "dtype": str(df[column].dtype),
        }
        group_by = params.get("group_by")
        if group_by:
            entry["by_group"] = {
                str(key): int(frame[column].isna().sum())
                for key, frame in df.groupby(group_by, sort=False)
            }
        columns[column] = entry
    complete_rows = int(df[step.target_columns].dropna().shape[0])
    return {
        "row_count": total,
        "complete_rows": complete_rows,
        "columns": columns,
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
    strategy_steps: list[str] = []
    normal, normal_steps = _normal_step(groups[:2])
    strategy_steps.extend(normal_steps)
    homogeneous, levene_steps = _levene_step(groups[:2])
    strategy_steps.extend(levene_steps)
    strategy_steps.extend(_imbalance_step(groups[:2]))

    requested = params.get("test", "auto")
    alternatives = {"t": "mannwhitney", "welch_t": "mannwhitney", "mannwhitney": "t"}
    if requested != "auto":
        final_method = requested
        strategy_steps.append(f"用户指定检验方法：{requested}（仍建议参考上述判定）")
    elif normal and homogeneous:
        final_method = "t"
    elif normal and not homogeneous:
        final_method = "welch_t"
        strategy_steps.append("正态但方差不齐 → 选择 Welch t（不假设等方差）")
    else:
        final_method = "mannwhitney"
        strategy_steps.append("非正态 → 选择 Mann-Whitney U（秩检验）")
    alternative = alternatives.get(final_method, "permutation")

    if final_method == "mannwhitney":
        statistic, p_value = sp_stats.mannwhitneyu(values_a, values_b, alternative="two-sided")
    elif params.get("paired"):
        length = min(len(values_a), len(values_b))
        statistic, p_value = sp_stats.ttest_rel(values_a[:length], values_b[:length])
    else:
        statistic, p_value = sp_stats.ttest_ind(values_a, values_b, equal_var=False)

    diff = float(values_a.mean() - values_b.mean())
    se = float(np.sqrt(values_a.var(ddof=1) / len(values_a) + values_b.var(ddof=1) / len(values_b)))
    alpha = _alpha(params)
    result: dict[str, Any] = {
        "column": column,
        "group_column": group_column,
        "groups": {name_a: int(len(values_a)), name_b: int(len(values_b))},
        "group_means": {name_a: float(values_a.mean()), name_b: float(values_b.mean())},
        "test": final_method,
        "statistic": float(statistic),
        "p_value": float(p_value),
        "mean_diff": diff,
        "ci95": [diff - 1.96 * se, diff + 1.96 * se],
        "cohens_d": cohens_d(values_a, values_b),
        "strategy": {
            "steps": strategy_steps,
            "final_method": final_method,
            "alternative": f"次优：{alternative}（当检验前提变化时使用）",
        },
        "note": "p 值仅作参考，须同时报告效应量与 95%CI",
    }
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
    }
    attach_significance(result, "p_value", alpha)

    if len(groups) >= 3:
        correction = params.get("correction", "holm")
        rows: list[dict[str, Any]] = []
        raw_p: list[float] = []
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                name_i, values_i = groups[i]
                name_j, values_j = groups[j]
                if test == "anova":
                    stat, pair_p = sp_stats.ttest_ind(values_i, values_j, equal_var=False)
                else:
                    stat, pair_p = sp_stats.mannwhitneyu(values_i, values_j, alternative="two-sided")
                raw_p.append(float(pair_p))
                rows.append(
                    {
                        "group_a": name_i,
                        "group_b": name_j,
                        "statistic": float(stat),
                        "p_value": float(pair_p),
                    }
                )
        adjusted = p_adjust(raw_p, correction)
        for row, adj_p in zip(rows, adjusted):
            row["adjusted_p"] = adj_p
            row.update(significance_label(adj_p, alpha))
        result["pairwise"] = {"columns": list(rows[0].keys()) if rows else [], "rows": rows}
        result["table"] = result["pairwise"]
        result["multiplicity_warning"] = (
            f"多重检验提醒：多组两两比较未经校正会膨胀 I 类错误，已按 {correction} 做多重性校正；"
            "显著性判断以校正后 p 值（adjusted_p）为准"
        )
    return result


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

    sufficient = low_ratio <= 0.2 and min_expected >= 1
    is_2x2 = table.shape == (2, 2)
    alpha = _alpha(params)
    result: dict[str, Any] = {
        "row_column": row_column,
        "col_column": col_column,
        "table": table.to_dict(),
        "strategy": {"steps": strategy_steps, "final_method": "", "alternative": ""},
    }

    if sufficient:
        chi2, p_value, dof, _ = sp_stats.chi2_contingency(
            table, correction=bool(params.get("correction", True))
        )
        result.update(
            {
                "chi2": float(chi2),
                "dof": int(dof),
                "p_value": float(p_value),
            }
        )
        result["strategy"]["final_method"] = "chi_square"
        result["strategy"]["alternative"] = "次优：Fisher 精确检验（当期望频数条件不满足时）"
    elif is_2x2:
        odds_ratio, p_value = sp_stats.fisher_exact(table)
        result.update({"p_value": float(p_value), "odds_ratio": float(odds_ratio)})
        result["strategy"]["final_method"] = "fisher_exact"
        result["strategy"]["alternative"] = (
            "次优：增大样本量使期望频数满足卡方条件后改用卡方检验"
        )
        strategy_steps.append("2×2 表期望频数不足 → 自动改用 Fisher 精确检验（精确分布，不依赖大样本近似）")
    else:
        raise ValueError(
            f"R×C 表期望频数不足（最小期望 {min_expected:.2f}）：建议增大样本量，"
            "或将相邻类别合并后重新检验"
        )

    result["cramers_v"] = float(np.sqrt(result.get("chi2", 0) / (n * (min(table.shape) - 1)))) if n else 0.0
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
    result["note"] = "期望频数<5 的格子占比应≤20% 且最小期望≥1，否则卡方近似失效"
    return attach_significance(result, "p_value", alpha)


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
            else:
                r, p_value = sp_stats.pearsonr(frame[first], frame[second])
            pairs[f"{first}_{second}"] = {
                "r": float(r),
                "p_value": float(p_value),
                "n": int(len(frame)),
            }
            pairs[f"{first}_{second}"].update(significance_label(p_value, alpha))
    rounded = matrix.round(4).to_dict()
    pair_rows = [
        {"pair": key, **{k: value for k, value in stat.items() if k in ("r", "p_value", "stars")}}
        for key, stat in pairs.items()
    ]
    return {
        "method": method,
        "matrix": rounded,
        "correlation": rounded,  # 兼容旧契约
        "pairs": pairs,
        "table": {"columns": ["pair", "r", "p_value", "significance"], "rows": pair_rows},
    }


def regression(df: pd.DataFrame, step: Any, params: dict) -> dict:
    import statsmodels.api as sm

    target = params["target"]
    features = list(params["features"])
    frame = df[[target, *features]].apply(pd.to_numeric, errors="coerce").dropna()
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
    return {
        "target": target,
        "features": features,
        "n": int(model.nobs),
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "f_pvalue": float(model.f_pvalue),
        "alpha": alpha,
        "coefficients": coefficients,
        "table": {"columns": ["term", "estimate", "p_value", "significance"], "rows": coef_rows},
        "note": "线性回归假设：线性、独立、同方差、残差正态；违反时考虑稳健标准误或变换",
    }


def logistic_regression(df: pd.DataFrame, step: Any, params: dict) -> dict:
    import statsmodels.api as sm

    target = params["target"]
    features = list(params["features"])
    frame = df[[target, *features]].apply(pd.to_numeric, errors="coerce").dropna()
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
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
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

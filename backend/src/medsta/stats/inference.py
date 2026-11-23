"""推断统计补充方法（spec 024）：单样本检验、随机区组方差分析、配对四格表。

依据《医学统计学》第 8 版第七、八、九章。所有判定与计算为宿主确定性逻辑。
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from medsta.stats.notes import METHOD_NOTES
from medsta.stats.significance import attach_significance

_ALTERNATIVES = {"two": "two-sided", "greater": "greater", "less": "less"}


def _numeric(df: pd.DataFrame, column: str) -> np.ndarray:
    return pd.to_numeric(df[column], errors="coerce").dropna().to_numpy(dtype=float)


def _is_normal(values: np.ndarray, alpha: float = 0.05) -> tuple[bool, float]:
    if len(values) < 3 or len(np.unique(values)) < 3:
        return False, float("nan")
    p_value = float(sp_stats.shapiro(values).pvalue)
    skew = float(sp_stats.skew(values, bias=False))
    return p_value > alpha and abs(skew) <= 1.0, p_value


def _mean_ci(
    mean: float, se: float, df: float, alpha: float, sides: str
) -> list[float | None]:
    if sides == "two":
        critical = float(sp_stats.t.ppf(1 - alpha / 2, df))
        return [round(mean - critical * se, 4), round(mean + critical * se, 4)]
    critical = float(sp_stats.t.ppf(1 - alpha, df))
    if sides == "greater":
        return [round(mean - critical * se, 4), None]
    return [None, round(mean + critical * se, 4)]


def factorial_anova(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """两因素析因设计方差分析（A、B 及 A×B 交互）。

    平衡设计按正交平方和分解（`SS总=SS(A)+SS(B)+SS(AB)+SS误差`）；不平衡设计改用
    statsmodels 的 Type II 平方和（偏平方和，合计不等于 SS总）。
    """
    value_column = step.target_columns[0]
    factor_a = params["factor_a"]
    factor_b = params["factor_b"]
    raw_interaction = params.get("interaction", True)
    if isinstance(raw_interaction, bool):
        interaction = raw_interaction
    else:
        interaction = str(raw_interaction).lower() not in {"no", "false", "0", "off"}
    alpha = float(params.get("alpha", 0.05) or 0.05)

    frame = df[[value_column, factor_a, factor_b]].copy()
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna()
    frame["_a"] = frame[factor_a].astype(str)
    frame["_b"] = frame[factor_b].astype(str)

    a_levels = sorted(frame["_a"].unique())
    b_levels = sorted(frame["_b"].unique())
    a_count, b_count = len(a_levels), len(b_levels)
    if a_count < 2 or b_count < 2:
        raise ValueError(f"析因设计需要两个因素均至少 2 个水平（当前 {a_count}×{b_count}）")

    total_n = len(frame)
    cell_counts = frame.groupby(["_a", "_b"]).size()
    balanced = len(cell_counts) == a_count * b_count and cell_counts.nunique() == 1
    steps: list[str] = []

    if balanced:
        n_cell = int(cell_counts.iloc[0])
        grand = float(frame[value_column].mean())
        ss_total = float(((frame[value_column] - grand) ** 2).sum())
        mean_a = frame.groupby("_a")[value_column].mean()
        mean_b = frame.groupby("_b")[value_column].mean()
        cell_mean = frame.groupby(["_a", "_b"])[value_column].mean()

        ss_a = float(b_count * n_cell * ((mean_a - grand) ** 2).sum())
        ss_b = float(a_count * n_cell * ((mean_b - grand) ** 2).sum())
        ss_ab = 0.0
        if interaction:
            cell_expected = pd.Series(
                {
                    key: float(mean_a[key[0]]) + float(mean_b[key[1]]) - grand
                    for key in cell_mean.index
                }
            )
            ss_ab = float(n_cell * ((cell_mean - cell_expected) ** 2).sum())

        frame["_cell_mean"] = frame.groupby(["_a", "_b"])[value_column].transform("mean")
        ss_error = float(((frame[value_column] - frame["_cell_mean"]) ** 2).sum())
        if not interaction:
            ss_error = ss_total - ss_a - ss_b

        df_a, df_b = a_count - 1, b_count - 1
        df_ab = df_a * df_b if interaction else 0
        df_error = (
            total_n - a_count * b_count if interaction else total_n - a_count - b_count + 1
        )
        ms_error = ss_error / df_error if df_error else 0.0
        if ms_error <= 0:
            raise ValueError("误差均方为 0，无法进行 F 检验（数据可能由因素完全决定）")
        f_a = float(ss_a / df_a / ms_error)
        f_b = float(ss_b / df_b / ms_error)
        p_a = float(sp_stats.f.sf(f_a, df_a, df_error))
        p_b = float(sp_stats.f.sf(f_b, df_b, df_error))
        f_ab = float(ss_ab / df_ab / ms_error) if interaction and df_ab else None
        p_ab = float(sp_stats.f.sf(f_ab, df_ab, df_error)) if f_ab is not None else None
        ss_type: Any = "balanced"
        steps.append(
            f"平衡析因设计：{a_count}×{b_count}，每格 {n_cell} 个观测，按 SS总=SS(A)+SS(B)+SS(AB)+SS误差 正交分解"
        )
    else:
        from statsmodels.formula.api import ols
        from statsmodels.stats.anova import anova_lm

        work = frame.rename(columns={value_column: "_y", factor_a: "_fa", factor_b: "_fb"})
        formula = "_y ~ C(_fa) * C(_fb)" if interaction else "_y ~ C(_fa) + C(_fb)"
        table = anova_lm(ols(formula, data=work).fit(), typ=2)

        row_a = table.loc["C(_fa)"]
        row_b = table.loc["C(_fb)"]
        ss_a, df_a = float(row_a["sum_sq"]), int(row_a["df"])
        ss_b, df_b = float(row_b["sum_sq"]), int(row_b["df"])
        f_a, p_a = float(row_a["F"]), float(row_a["PR(>F)"])
        f_b, p_b = float(row_b["F"]), float(row_b["PR(>F)"])
        if interaction:
            row_ab = table.loc["C(_fa):C(_fb)"]
            ss_ab, df_ab = float(row_ab["sum_sq"]), int(row_ab["df"])
            f_ab, p_ab = float(row_ab["F"]), float(row_ab["PR(>F)"])
        else:
            ss_ab, df_ab, f_ab, p_ab = 0.0, 0, None, None
        ss_error, df_error = float(table.loc["Residual", "sum_sq"]), int(table.loc["Residual", "df"])
        ms_error = ss_error / df_error if df_error else 0.0
        grand = float(frame[value_column].mean())
        ss_total = float(((frame[value_column] - grand) ** 2).sum())
        ss_type = 2
        steps.append(
            "不平衡设计（每格样本量不等）→ 改用 Type II 平方和；各效应为偏平方和，合计不等于 SS总"
        )

    if interaction and p_ab is not None and p_ab < alpha:
        steps.append(f"交互效应显著（P={p_ab:.4g}）：主效应解释需谨慎，应进一步做简单效应分析")
    elif interaction:
        steps.append("交互效应不显著：可主要解释主效应")

    rows: list[dict[str, Any]] = [
        {
            "source": "A",
            "ss": round(ss_a, 6),
            "df": df_a,
            "ms": round(ss_a / df_a, 6) if df_a else None,
            "f": round(f_a, 4),
            "p_value": p_a,
        },
        {
            "source": "B",
            "ss": round(ss_b, 6),
            "df": df_b,
            "ms": round(ss_b / df_b, 6) if df_b else None,
            "f": round(f_b, 4),
            "p_value": p_b,
        },
    ]
    if interaction:
        rows.append(
            {
                "source": "A×B",
                "ss": round(ss_ab, 6),
                "df": df_ab,
                "ms": round(ss_ab / df_ab, 6) if df_ab else None,
                "f": round(f_ab, 4) if f_ab is not None else None,
                "p_value": p_ab,
            }
        )
    rows.extend(
        [
            {
                "source": "误差",
                "ss": round(ss_error, 6),
                "df": df_error,
                "ms": round(ms_error, 6),
                "f": None,
                "p_value": None,
            },
            {
                "source": "总",
                "ss": round(ss_total, 6),
                "df": df_a + df_b + df_ab + df_error,
                "ms": None,
                "f": None,
                "p_value": None,
            },
        ]
    )

    result: dict[str, Any] = {
        "column": value_column,
        "factor_a": factor_a,
        "factor_b": factor_b,
        "levels": {"a": a_count, "b": b_count},
        "n": total_n,
        "interaction_included": interaction,
        "ss_type": ss_type,
        "ss_total": ss_total,
        "ss_a": ss_a,
        "ss_b": ss_b,
        "ss_ab": ss_ab,
        "ss_error": ss_error,
        "df_a": df_a,
        "df_b": df_b,
        "df_ab": df_ab,
        "df_error": df_error,
        "ms_error": ms_error,
        "f_a": f_a,
        "p_a": p_a,
        "f_b": f_b,
        "p_b": p_b,
        "f_ab": f_ab,
        "p_ab": p_ab,
        "alpha": alpha,
        "strategy": {
            "steps": steps,
            "final_method": "factorial_anova",
            "alternative": "次优：对每个因素分别做单因素方差分析（会忽略交互作用）",
        },
        "table": {
            "columns": ["source", "ss", "df", "ms", "f", "p_value"],
            "rows": rows,
        },
        "method_note": METHOD_NOTES["factorial_anova"],
    }
    return attach_significance(result, "p_a", alpha)


def repeated_measures_anova(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """单因素重复测量方差分析（同一受试者多个时间点/条件）。"""
    value_column = step.target_columns[0]
    subject_column = params["subject_column"]
    within_column = params["within_column"]
    alpha = float(params.get("alpha", 0.05) or 0.05)

    frame = df[[value_column, subject_column, within_column]].copy()
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna()
    frame["_subject"] = frame[subject_column].astype(str)
    frame["_within"] = frame[within_column].astype(str)

    within_levels = sorted(frame["_within"].unique())
    subject_count = int(frame["_subject"].nunique())
    if len(within_levels) < 2:
        raise ValueError(f"重复测量需要组内因素至少 2 个水平（当前 {len(within_levels)}）")
    if subject_count < 2:
        raise ValueError(f"重复测量至少需要 2 名受试者（当前 {subject_count}）")

    cell_counts = frame.groupby(["_subject", "_within"]).size()
    if (cell_counts != 1).any() or len(cell_counts) != subject_count * len(within_levels):
        raise ValueError(
            "重复测量要求每个受试者在每个时间点恰有 1 个观测；当前数据不平衡或存在缺失，"
            "建议改用线性混合模型（MixedLM）"
        )

    k = len(within_levels)
    n = subject_count
    grand = float(frame[value_column].mean())
    ss_total = float(((frame[value_column] - grand) ** 2).sum())
    subject_mean = frame.groupby("_subject")[value_column].mean()
    within_mean = frame.groupby("_within")[value_column].mean()
    ss_subject = float(k * ((subject_mean - grand) ** 2).sum())
    ss_time = float(n * ((within_mean - grand) ** 2).sum())
    ss_error = float(ss_total - ss_subject - ss_time)

    df_time = k - 1
    df_subject = n - 1
    df_error = df_time * df_subject
    ms_error = ss_error / df_error if df_error else 0.0
    if ms_error <= 0:
        raise ValueError("误差均方为 0，无法进行 F 检验（数据可能由时间与个体完全决定）")
    f_time = float(ss_time / df_time / ms_error)
    p_time = float(sp_stats.f.sf(f_time, df_time, df_error))

    steps = [
        f"单因素重复测量：{n} 名受试者 × {k} 个水平，每个受试者×水平恰 1 个观测",
        f"SS总=SS时间+SS受试者+SS误差；F={f_time:.4g}（ν={df_time},{df_error}），P={p_time:.4g}",
        "本实现未做球形性校正：若 Mauchly 检验提示违反球形假设，应改用 Greenhouse-Geisser 校正或线性混合模型",
    ]

    result: dict[str, Any] = {
        "column": value_column,
        "subject_column": subject_column,
        "within_column": within_column,
        "n_subjects": n,
        "n_levels": k,
        "ss_total": ss_total,
        "ss_time": ss_time,
        "ss_subject": ss_subject,
        "ss_error": ss_error,
        "df_time": df_time,
        "df_subject": df_subject,
        "df_error": df_error,
        "ms_time": ss_time / df_time if df_time else None,
        "ms_error": ms_error,
        "f_time": f_time,
        "p_time": p_time,
        "alpha": alpha,
        "sphericity_corrected": False,
        "strategy": {
            "steps": steps,
            "final_method": "repeated_measures_anova",
            "alternative": "次优：Friedman 检验（不满足正态或球形假设时）",
        },
        "table": {
            "columns": ["source", "ss", "df", "ms", "f", "p_value"],
            "rows": [
                {
                    "source": "时间（组内）",
                    "ss": round(ss_time, 6),
                    "df": df_time,
                    "ms": round(ss_time / df_time, 6) if df_time else None,
                    "f": round(f_time, 4),
                    "p_value": p_time,
                },
                {
                    "source": "受试者间",
                    "ss": round(ss_subject, 6),
                    "df": df_subject,
                    "ms": round(ss_subject / df_subject, 6) if df_subject else None,
                    "f": None,
                    "p_value": None,
                },
                {
                    "source": "误差",
                    "ss": round(ss_error, 6),
                    "df": df_error,
                    "ms": round(ms_error, 6),
                    "f": None,
                    "p_value": None,
                },
                {
                    "source": "总",
                    "ss": round(ss_total, 6),
                    "df": df_time + df_subject + df_error,
                    "ms": None,
                    "f": None,
                    "p_value": None,
                },
            ],
        },
        "method_note": METHOD_NOTES["repeated_measures_anova"],
    }
    return attach_significance(result, "p_time", alpha)


_SAMPLE_DESIGNS = (
    "one_mean",
    "two_means",
    "paired_means",
    "two_proportions",
    "anova",
    "correlation",
)


def sample_size(df: Any, step: Any, params: dict) -> dict:
    """样本量与检验效能（设计期工具，不读取数据）。"""
    from statsmodels.stats.power import (
        FTestAnovaPower,
        NormalIndPower,
        TTestIndPower,
        TTestPower,
    )

    design = str(params.get("design", "two_means") or "two_means")
    if design not in _SAMPLE_DESIGNS:
        raise ValueError(f"未知设计类型：{design}（可选：{', '.join(_SAMPLE_DESIGNS)}）")
    solve = str(params.get("solve", "n") or "n")
    if solve not in ("n", "power"):
        raise ValueError(f"solve 只支持 n 或 power，收到 {solve}")

    alpha = float(params.get("alpha", 0.05) or 0.05)
    power_target = float(params.get("power", 0.8) or 0.8)
    ratio = float(params.get("ratio", 1.0) or 1.0)
    k_groups = int(params.get("k_groups", 3) or 3)
    given_n = params.get("n")

    effect_size = params.get("effect_size")
    if effect_size is None:
        delta = params.get("delta")
        sigma = params.get("sigma")
        if delta is None or sigma in (None, 0):
            raise ValueError(
                "sample_size 需要 effect_size（标准化效应量），或同时提供 delta（差值）与 sigma（标准差）"
            )
        effect_size = float(delta) / float(sigma)
    effect_size = abs(float(effect_size))
    if effect_size < 1e-12:
        raise ValueError("effect_size 不能为 0，否则样本量无解")

    if solve == "power" and given_n in (None, 0):
        raise ValueError("solve=power 时需要提供 n")

    n_per_group: int
    power: float
    total_n: int

    if design in ("one_mean", "paired_means"):
        solver = TTestPower()
        if solve == "power":
            n_per_group = int(math.ceil(float(given_n or 0)))
            power = float(
                solver.power(effect_size=effect_size, nobs=n_per_group, alpha=alpha)
            )
        else:
            raw = float(
                solver.solve_power(
                    effect_size=effect_size, alpha=alpha, power=power_target
                )
            )
            n_per_group = int(math.ceil(raw))
            power = float(
                solver.power(effect_size=effect_size, nobs=n_per_group, alpha=alpha)
            )
        total_n = n_per_group
        formula = "单样本/配对 t：n = (z_{α/2}+z_β)²/d²（TTestPower 迭代求根）"
    elif design == "two_means":
        solver_ind = TTestIndPower()
        if solve == "power":
            n_per_group = int(math.ceil(float(given_n or 0)))
            power = float(
                solver_ind.power(
                    effect_size=effect_size, nobs1=n_per_group, alpha=alpha, ratio=ratio
                )
            )
        else:
            raw = float(
                solver_ind.solve_power(
                    effect_size=effect_size, alpha=alpha, power=power_target, ratio=ratio
                )
            )
            n_per_group = int(math.ceil(raw))
            power = float(
                solver_ind.power(
                    effect_size=effect_size, nobs1=n_per_group, alpha=alpha, ratio=ratio
                )
            )
        total_n = n_per_group + int(math.ceil(n_per_group * ratio))
        formula = "两独立均数：n/组 = 2σ²(z_{α/2}+z_β)²/δ²（TTestIndPower 迭代求根）"
    elif design == "two_proportions":
        solver_norm = NormalIndPower()
        if solve == "power":
            n_per_group = int(math.ceil(float(given_n or 0)))
            power = float(
                solver_norm.power(
                    effect_size=effect_size, nobs1=n_per_group, alpha=alpha, ratio=ratio
                )
            )
        else:
            raw = float(
                solver_norm.solve_power(
                    effect_size=effect_size, alpha=alpha, power=power_target, ratio=ratio
                )
            )
            n_per_group = int(math.ceil(raw))
            power = float(
                solver_norm.power(
                    effect_size=effect_size, nobs1=n_per_group, alpha=alpha, ratio=ratio
                )
            )
        total_n = n_per_group + int(math.ceil(n_per_group * ratio))
        formula = "两独立率：基于 Cohen's h 的正态近似（NormalIndPower）"
    elif design == "anova":
        solver_anova = FTestAnovaPower()
        if solve == "power":
            n_per_group = int(math.ceil(float(given_n or 0)))
            power = float(
                solver_anova.power(
                    effect_size=effect_size,
                    nobs=n_per_group * k_groups,
                    alpha=alpha,
                    k_groups=k_groups,
                )
            )
        else:
            raw = float(
                solver_anova.solve_power(
                    effect_size=effect_size,
                    alpha=alpha,
                    power=power_target,
                    k_groups=k_groups,
                )
            )
            n_per_group = int(math.ceil(raw))
            power = float(
                solver_anova.power(
                    effect_size=effect_size,
                    nobs=n_per_group * k_groups,
                    alpha=alpha,
                    k_groups=k_groups,
                )
            )
        total_n = n_per_group * k_groups
        formula = "单因素方差分析：Cohen's f 与 FTestAnovaPower"
    else:  # correlation
        solver_corr = NormalIndPower()
        if solve == "power":
            n_per_group = int(math.ceil(float(given_n or 0)))
            power = float(
                solver_corr.power(effect_size=effect_size, nobs1=n_per_group, alpha=alpha)
            )
        else:
            raw = float(
                solver_corr.solve_power(
                    effect_size=effect_size, alpha=alpha, power=power_target
                )
            )
            n_per_group = int(math.ceil(raw))
            power = float(
                solver_corr.power(effect_size=effect_size, nobs1=n_per_group, alpha=alpha)
            )
        total_n = n_per_group
        formula = "相关分析：Fisher z 变换后按正态近似（效应量 = 0.5·ln((1+r)/(1−r))）"

    result: dict[str, Any] = {
        "design": design,
        "solve": solve,
        "effect_size": round(effect_size, 6),
        "alpha": alpha,
        "target_power": power_target,
        "power": round(power, 6),
        "n_per_group": n_per_group,
        "total_n": total_n,
        "k_groups": k_groups if design == "anova" else None,
        "formula": formula,
        "strategy": {
            "steps": [
                f"设计类型：{design}；solve={solve}；α={alpha}；目标效能={power_target}",
                f"标准化效应量 {effect_size:.4g}；每组 n={n_per_group}，合计 {total_n}",
                f"实际效能 {power:.4f}（n 取整后重新计算）",
            ],
            "final_method": "sample_size",
            "alternative": "若效应量不确定，应按最小临床意义差值做敏感性分析（多组 n 取最大）",
        },
        "table": {
            "columns": ["design", "effect_size", "alpha", "power", "n_per_group", "total_n"],
            "rows": [
                {
                    "design": design,
                    "effect_size": round(effect_size, 6),
                    "alpha": alpha,
                    "power": round(power, 6),
                    "n_per_group": n_per_group,
                    "total_n": total_n,
                }
            ],
        },
        "method_note": METHOD_NOTES["sample_size"],
    }
    return result


def mcnemar_test(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """配对四格表 McNemar 检验（教材 §9-2，公式 9-7/9-8）。"""
    row_column = params.get("row_column") or step.target_columns[0]
    col_column = params.get("col_column") or (
        step.target_columns[1] if len(step.target_columns) > 1 else None
    )
    if not col_column:
        raise ValueError("配对四格表需要两个二分类变量")
    table = pd.crosstab(df[row_column], df[col_column])
    if table.shape != (2, 2):
        raise ValueError(
            f"配对四格表需要两个二分类变量，当前列联表为 {table.shape[0]}×{table.shape[1]}"
        )

    d = int(table.iloc[0, 0])
    c = int(table.iloc[0, 1])
    b = int(table.iloc[1, 0])
    a = int(table.iloc[1, 1])
    discordant = b + c
    corrected = discordant < 40
    if discordant == 0:
        chi2 = 0.0
        p_value = 1.0
        steps = ["两法结果完全一致（b+c=0），无法检验差异"]
    elif corrected:
        chi2 = (abs(b - c) - 1) ** 2 / discordant
        p_value = float(sp_stats.chi2.sf(chi2, 1))
        steps = [f"b+c={discordant}<40 → 采用校正公式 χ²=(|b−c|−1)²/(b+c)"]
    else:
        chi2 = (b - c) ** 2 / discordant
        p_value = float(sp_stats.chi2.sf(chi2, 1))
        steps = [f"b+c={discordant}≥40 → 采用专用公式 χ²=(b−c)²/(b+c)"]

    total = a + b + c + d
    agreement_rate = (a + d) / total if total else 0.0
    # 单元格含义按列联表真实水平生成（P1 修复）：crosstab 按字典序排水平，
    # 硬编码「阳/阴」文案在中文编码（阳 U+9633 < 阴 U+9634）下会互换贴错格子
    row_hi, row_lo = str(table.index[1]), str(table.index[0])
    col_hi, col_lo = str(table.columns[1]), str(table.columns[0])
    if row_hi == col_hi:
        meaning_a = f"两法均为「{row_hi}」（一致）"
        meaning_d = f"两法均为「{row_lo}」（一致）"
    else:
        meaning_a = f"「{row_column}」=「{row_hi}」且「{col_column}」=「{col_hi}」（一致）"
        meaning_d = f"「{row_column}」=「{row_lo}」且「{col_column}」=「{col_lo}」（一致）"
    result: dict[str, Any] = {
        "row_column": row_column,
        "col_column": col_column,
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "n": total,
        "chi2": float(chi2),
        "corrected": corrected,
        "p_value": p_value,
        "agreement_rate": round(agreement_rate, 6),
        "strategy": {
            "steps": steps + ["配对四格表只能用配对 χ²，不能转为独立样本 χ²（教材 §9-2）"],
            "final_method": "mcnemar_corrected" if corrected else "mcnemar",
            "alternative": "次优：增大样本后改用专用公式" if corrected else "次优：b+c<40 时用校正公式",
        },
        "table": {
            "columns": ["cell", "count", "meaning"],
            "rows": [
                {"cell": "a", "count": a, "meaning": meaning_a},
                {"cell": "b", "count": b,
                 "meaning": f"「{row_column}」=「{row_hi}」且「{col_column}」=「{col_lo}」（不一致）"},
                {"cell": "c", "count": c,
                 "meaning": f"「{row_column}」=「{row_lo}」且「{col_column}」=「{col_hi}」（不一致）"},
                {"cell": "d", "count": d, "meaning": meaning_d},
            ],
        },
        "method_note": METHOD_NOTES["mcnemar_test"],
    }
    return attach_significance(result, "p_value", float(params.get("alpha", 0.05) or 0.05))


def randomized_block_anova(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """随机区组设计方差分析（教材 §8-3）。

    要求每个「处理 × 区组」单元恰有 1 个观测（教材的标准随机区组设计）。
    """
    column = step.target_columns[0]
    group_column = params["group_column"]
    block_column = params["block_column"]
    alpha = float(params.get("alpha", 0.05) or 0.05)

    frame = df[[column, group_column, block_column]].copy()
    frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna()
    frame["_group"] = frame[group_column].astype(str)
    frame["_block"] = frame[block_column].astype(str)

    group_count = frame["_group"].nunique()
    block_count = frame["_block"].nunique()
    if group_count < 2:
        raise ValueError(f"处理因素「{group_column}」不足 2 个水平")
    if block_count < 2:
        raise ValueError(f"区组因素「{block_column}」不足 2 个水平")

    cell_counts = frame.groupby(["_group", "_block"]).size()
    if (cell_counts != 1).any():
        raise ValueError("随机区组设计要求每个处理×区组单元恰有 1 个观测；有重复时应改用两因素方差分析")
    if len(cell_counts) != group_count * block_count:
        raise ValueError("随机区组设计不完整：存在缺失的处理×区组单元格")

    values = frame[column]
    grand = float(values.mean())
    ss_total = float(((values - grand) ** 2).sum())
    group_means = values.groupby(frame["_group"]).mean()
    block_means = values.groupby(frame["_block"]).mean()
    ss_treatment = float(block_count * ((group_means - grand) ** 2).sum())
    ss_block = float(group_count * ((block_means - grand) ** 2).sum())
    ss_error = float(ss_total - ss_treatment - ss_block)

    df_treatment = group_count - 1
    df_block = block_count - 1
    df_error = df_treatment * df_block
    ms_treatment = ss_treatment / df_treatment
    ms_block = ss_block / df_block
    ms_error = ss_error / df_error if df_error else 0.0
    if ms_error <= 0:
        raise ValueError("误差均方为 0，无法进行 F 检验（数据可能完全由处理与区组决定）")

    f_treatment = ms_treatment / ms_error
    p_treatment = float(sp_stats.f.sf(f_treatment, df_treatment, df_error))
    f_block = ms_block / ms_error
    p_block = float(sp_stats.f.sf(f_block, df_block, df_error))

    result: dict[str, Any] = {
        "column": column,
        "group_column": group_column,
        "block_column": block_column,
        "n": int(len(frame)),
        "levels": {"treatment": group_count, "block": block_count},
        "ss_total": ss_total,
        "ss_treatment": ss_treatment,
        "ss_block": ss_block,
        "ss_error": ss_error,
        "df_treatment": df_treatment,
        "df_block": df_block,
        "df_error": df_error,
        "ms_treatment": ms_treatment,
        "ms_block": ms_block,
        "ms_error": ms_error,
        "f_treatment": f_treatment,
        "p_treatment": p_treatment,
        "f_block": f_block,
        "p_block": p_block,
        "alpha": alpha,
        "strategy": {
            "steps": [
                f"随机区组设计：{group_count} 个处理 × {block_count} 个区组，每单元 1 个观测",
                f"处理效应 F={f_treatment:.4g}（ν={df_treatment},{df_error}），P={p_treatment:.4g}",
                f"区组效应 F={f_block:.4g}（ν={df_block},{df_error}），P={p_block:.4g}",
            ],
            "final_method": "randomized_block_anova",
            "alternative": "次优：Friedman 检验（不满足正态或方差齐性时）",
        },
        "table": {
            "columns": ["source", "ss", "df", "ms", "f", "p_value"],
            "rows": [
                {
                    "source": "处理",
                    "ss": round(ss_treatment, 6),
                    "df": df_treatment,
                    "ms": round(ms_treatment, 6),
                    "f": round(f_treatment, 4),
                    "p_value": p_treatment,
                },
                {
                    "source": "区组",
                    "ss": round(ss_block, 6),
                    "df": df_block,
                    "ms": round(ms_block, 6),
                    "f": round(f_block, 4),
                    "p_value": p_block,
                },
                {
                    "source": "误差",
                    "ss": round(ss_error, 6),
                    "df": df_error,
                    "ms": round(ms_error, 6),
                    "f": None,
                    "p_value": None,
                },
                {
                    "source": "总",
                    "ss": round(ss_total, 6),
                    "df": df_treatment + df_block + df_error,
                    "ms": None,
                    "f": None,
                    "p_value": None,
                },
            ],
        },
        "method_note": METHOD_NOTES["randomized_block_anova"],
    }
    return attach_significance(result, "p_treatment", alpha)


def one_sample_test(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """单样本 t 检验 / Wilcoxon 符号秩（教材 §7-1、§10-1）。"""
    column = step.target_columns[0]
    mu0 = float(params["mu0"])
    requested = str(params.get("test", "auto") or "auto")
    sides = str(params.get("sides", "two") or "two")
    if sides not in _ALTERNATIVES:
        raise ValueError(f"未知单双侧设定：{sides}")
    alpha = float(params.get("alpha", 0.05) or 0.05)

    values = _numeric(df, column)
    n = len(values)
    if n < 3:
        raise ValueError(f"列「{column}」有效观测仅 {n} 个，单样本检验至少需要 3 个")

    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    se = sd / math.sqrt(n)
    normal, shapiro_p = _is_normal(values, alpha)
    steps: list[str] = [
        f"正态性（Shapiro-Wilk）：n={n}, p={shapiro_p:.4g} → {'近似正态' if normal else '非正态'}"
    ]

    if requested == "auto":
        final_method = "t" if normal else "wilcoxon"
        steps.append(
            "近似正态 → 选择单样本 t 检验" if normal else "非正态 → 选择 Wilcoxon 符号秩检验"
        )
    else:
        final_method = requested
        steps.append(f"用户指定检验方法：{requested}（仍建议参考上述判定）")

    alternative = _ALTERNATIVES[sides]
    if final_method == "t":
        statistic, p_value = sp_stats.ttest_1samp(values, mu0, alternative=alternative)
        df_value = float(n - 1)
        ci95 = _mean_ci(mean, se, df_value, alpha, sides)
        ci_method = "t"
    else:
        statistic, p_value = sp_stats.wilcoxon(values - mu0, alternative=alternative)
        df_value = None
        ci95 = [None, None]
        ci_method = "none"

    result: dict[str, Any] = {
        "column": column,
        "mu0": mu0,
        "n": n,
        "mean": round(mean, 4),
        "sd": round(sd, 4),
        "se": round(se, 4),
        "median": round(float(np.median(values)), 4),
        "mean_diff": round(mean - mu0, 4),
        "test": final_method,
        "statistic": float(statistic),
        "df": df_value,
        "p_value": float(p_value),
        "ci95": ci95,
        "ci_method": ci_method,
        "sides": sides,
        "strategy": {
            "steps": steps,
            "final_method": final_method,
            "alternative": (
                "次优：Wilcoxon 符号秩（非参数）" if final_method == "t" else "次优：单样本 t（需正态）"
            ),
        },
        "table": {
            "columns": ["test", "statistic", "df", "p_value", "mean_diff", "ci_low", "ci_high"],
            "rows": [
                {
                    "test": final_method,
                    "statistic": float(statistic),
                    "df": df_value,
                    "p_value": float(p_value),
                    "mean_diff": round(mean - mu0, 4),
                    "ci_low": ci95[0],
                    "ci_high": ci95[1],
                }
            ],
        },
        "method_note": METHOD_NOTES["one_sample_test"],
    }
    return attach_significance(result, "p_value", alpha)

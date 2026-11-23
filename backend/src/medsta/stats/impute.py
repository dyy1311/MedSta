"""缺失数据诊断与插补（spec 028）。

教材《医学统计学》第 8 版未覆盖缺失数据，本模块依据外部标准：
Little & Rubin (2019) 的缺失机制分类、van Buuren (2018) 的 MICE。
"""
from __future__ import annotations

import pathlib
from typing import Any

import numpy as np
import pandas as pd

from medsta.stats.notes import METHOD_NOTES

MISSING_REJECT_SHARE = 0.5
M_DEFAULT = 20
M_MAX = 50
M_RECOMMENDED = 20
DEFAULT_RANDOM_STATE = 20261023


def impute_mice(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    m: int,
    max_iter: int,
    random_state: int,
) -> tuple[pd.DataFrame, float]:
    """MICE（链式方程）：运行 m 次后取逐元素均值，并返回插补间方差均值。"""
    from sklearn.experimental import enable_iterative_imputer  # noqa: F401
    from sklearn.impute import IterativeImputer

    data = frame[columns].astype(float)
    missing_mask = data.isna().to_numpy()
    if not missing_mask.any() or m < 2:
        return data.copy(), 0.0

    samples = []
    for index in range(m):
        imputer = IterativeImputer(
            max_iter=max_iter,
            random_state=random_state + index,
            sample_posterior=True,
        )
        samples.append(imputer.fit_transform(data))
    stacked = np.stack(samples)
    mean_values = stacked.mean(axis=0)

    filled = data.to_numpy(copy=True)
    filled[missing_mask] = mean_values[missing_mask]
    # 插补间方差只在缺失格计算（M19）：观测格各次插补相同（方差恒 0），
    # 计入均值会按缺失占比系统性低估 between-imputation variance
    between_variance = float(
        np.mean(np.var(stacked[:, missing_mask], axis=0, ddof=1))
    )
    return pd.DataFrame(filled, columns=columns, index=frame.index), between_variance


def impute_simple(frame: pd.DataFrame, columns: list[str], method: str) -> pd.DataFrame:
    """均值/中位数/LOCF：仅用于敏感性分析。"""
    data = frame[columns].astype(float)
    if method == "locf":
        return data.ffill().bfill()
    from sklearn.impute import SimpleImputer

    strategy = "median" if method == "median" else "mean"
    filled = SimpleImputer(strategy=strategy).fit_transform(data)
    return pd.DataFrame(filled, columns=columns, index=frame.index)


def delta_scan(
    frame: pd.DataFrame,
    columns: list[str],
    filled: pd.DataFrame,
    delta: float,
) -> dict[str, Any]:
    """对插补值整体加减 delta，输出均值与标准差的偏移。"""
    missing_mask = frame[columns].isna()
    rows: list[dict[str, Any]] = []
    for column in columns:
        mask = missing_mask[column].to_numpy()
        if not mask.any():
            continue
        for shift in (-delta, 0.0, delta):
            adjusted = filled[column].to_numpy(dtype=float, copy=True)
            adjusted[mask] += shift
            rows.append(
                {
                    "column": column,
                    "delta": shift,
                    "mean": round(float(np.mean(adjusted)), 6),
                    "sd": round(float(np.std(adjusted, ddof=1)), 6),
                }
            )
    return {"columns": ["column", "delta", "mean", "sd"], "rows": rows}


def impute(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """工具入口：插补并（在提供工作区目录时）产出可继续分析的数据集。"""
    columns = list(params.get("columns") or step.target_columns or [])
    if not columns:
        raise ValueError("插补需要指定至少 1 个目标列")
    absent = [column for column in columns if column not in df.columns]
    if absent:
        raise ValueError(f"列不存在：{', '.join(absent)}")

    method = str(params.get("method", "mice") or "mice")
    if method not in ("mice", "median", "mean", "locf"):
        raise ValueError(f"未知插补方法：{method}")
    m_value = int(params.get("m", M_DEFAULT) or M_DEFAULT)
    max_iter = int(params.get("max_iter", 10) or 10)
    random_state = int(params.get("random_state", DEFAULT_RANDOM_STATE) or DEFAULT_RANDOM_STATE)
    raw_delta = params.get("delta")
    artifact_dir = params.get("_artifact_dir")
    alpha = float(params.get("alpha", 0.05) or 0.05)

    warnings: list[str] = []
    for column in columns:
        share = float(df[column].isna().mean())
        if share > MISSING_REJECT_SHARE:
            raise ValueError(
                f"列「{column}」缺失 {share:.0%}（>50%），建议删除该列而非插补"
            )
        if int(df[column].notna().sum()) < 2:
            raise ValueError(f"列「{column}」有效观测不足 2 个，无法插补")

    m = max(2, min(m_value, M_MAX))
    if m_value < M_RECOMMENDED:
        warnings.append(
            f"m={m_value} 少于建议的 {M_RECOMMENDED} 次，插补不确定性估计不稳定"
        )
    if m_value > M_MAX:
        warnings.append(f"m={m_value} 超过上限 {M_MAX}，已截断以控制耗时")

    if method == "mice":
        filled, between_variance = impute_mice(
            df, columns, m=m, max_iter=max_iter, random_state=random_state
        )
    else:
        filled = impute_simple(df, columns, method)
        between_variance = 0.0
        warnings.append(
            f"method={method} 属单值插补，仅供敏感性分析，不应作为主分析结果"
        )

    imputed = df.copy()
    for column in columns:
        imputed[column] = filled[column].to_numpy()

    missing_before = {column: int(df[column].isna().sum()) for column in columns}
    missing_after = {column: int(imputed[column].isna().sum()) for column in columns}
    sensitivity_only = method != "mice"

    dataset: dict[str, Any] | None = None
    if sensitivity_only:
        pass
    elif not artifact_dir:
        warnings.append(
            "未提供工作区目录，插补结果未落盘；请在统计步骤中执行以生成可继续分析的数据集"
        )
    else:
        target = pathlib.Path(artifact_dir)
        target.mkdir(parents=True, exist_ok=True)
        # 按步骤索引命名（M20）：同计划多个插补步骤不再互相覆盖
        step_index = int(params.get("_step_index", 0) or 0)
        path = target / f"imputed_step_{step_index}.csv"
        imputed.to_csv(path, index=False)
        dataset = {
            "path": str(path),
            "name": "插补数据集（MICE 插补）",
            "rows": int(len(imputed)),
            "columns": int(imputed.shape[1]),
            "missing_before": int(sum(missing_before.values())),
            "missing_after": int(sum(missing_after.values())),
            "method": method,
            "m": m,
        }

    scan: dict[str, Any] | None = None
    if raw_delta not in (None, ""):
        try:
            delta_value = float(raw_delta)
        except (TypeError, ValueError):
            raise ValueError(f"delta 必须为数值，收到 {raw_delta!r}") from None
        if delta_value < 0:
            raise ValueError("delta 应为非负数（内部会同时扫描 ±delta）")
        scan = delta_scan(df, columns, filled, delta_value)

    summary_rows = [
        {
            "column": column,
            "missing_before": missing_before[column],
            "missing_after": missing_after[column],
            "method": method,
            "m": m if method == "mice" else None,
        }
        for column in columns
    ]

    return {
        "columns": columns,
        "method": method,
        "m": m,
        "max_iter": max_iter,
        "n": int(len(df)),
        "missing_before": missing_before,
        "missing_after": missing_after,
        "imputed_dataset": dataset,
        "between_imputation_variance": round(between_variance, 8),
        "sensitivity_only": sensitivity_only,
        "delta_scan": scan,
        "warnings": warnings,
        "alpha": alpha,
        # 037 链间管道：插补后 DataFrame 传给同链后续步骤（executor 在 JSON 化前剥离）
        "_next_frame": imputed,
        "table": {
            "columns": ["column", "missing_before", "missing_after", "method", "m"],
            "rows": summary_rows,
        },
        "strategy": {
            "steps": [
                f"缺失处理：{method}，目标列 {len(columns)} 个，样本 {len(df)} 行",
                (
                    "MICE 运行 "
                    f"{m} 次取均值；产出为单数据集插补，非 Rubin 合并，标准误偏小"
                    if method == "mice"
                    else "单值插补仅作敏感性分析"
                ),
            ],
            "final_method": f"impute_{method}",
            "alternative": "完整多重插补 + Rubin 合并（未实现），或 MMRM（未实现）",
        },
        "method_note": METHOD_NOTES["impute"],
    }

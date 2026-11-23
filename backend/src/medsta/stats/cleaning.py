"""数据清洗层（045）：去重 / 筛选 / 标准化 / 分箱 / 异常值识别 / 截尾。

全部为确定性宿主计算（零模型参与）。数据产出型工具遵循 028 impute 的约定：
在工作区目录写 `cleaned_step_{i}.csv`（M20 同款按步骤索引命名），经
`_next_frame` 供同链后续步骤使用（037 链间管道），由 service 注册为新
数据集（dataset_added，imputed=false）。
"""
from __future__ import annotations

import pathlib
from typing import Any

import pandas as pd

_FILTER_OPS = {"eq", "ne", "gt", "ge", "lt", "le", "between", "in", "isna", "notna"}


def _cleaned_payload(
    frame: pd.DataFrame, params: dict, name: str, extra: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """写清洗产物数据集（无工作区目录时返回 None，调用方附提示）。"""
    artifact_dir = params.get("_artifact_dir")
    if not artifact_dir:
        return None
    target = pathlib.Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)
    step_index = int(params.get("_step_index", 0) or 0)
    path = target / f"cleaned_step_{step_index}.csv"
    frame.to_csv(path, index=False)
    payload: dict[str, Any] = {
        "path": str(path),
        "name": name,
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
    }
    if extra:
        payload.update(extra)
    return payload


def _emit_cleaned(
    frame: pd.DataFrame,
    params: dict,
    name: str,
) -> dict[str, Any] | None:
    """产出数据集并挂 `_next_frame`（037 链间管道内部键，registry 出口剥离）。"""
    result: dict[str, Any] = {"_next_frame": frame}
    payload = _cleaned_payload(frame, params, name)
    if payload is not None:
        result["cleaned_dataset"] = payload
    else:
        result["clean_warning"] = (
            "未提供工作区目录，清洗结果未落盘；请在统计步骤中执行以生成可继续分析的数据集"
        )
    return result


def _numeric_series(df: pd.DataFrame, column: str, action: str) -> pd.Series:
    """取数值化序列：列不存在 / 含非数值（会静默丢数据）时显式拒绝。"""
    if column not in df.columns:
        raise ValueError(f"列不存在：{column}")
    numeric = pd.to_numeric(df[column], errors="coerce")
    coerced_missing = int(numeric.isna().sum()) - int(df[column].isna().sum())
    if coerced_missing > 0:
        raise ValueError(f"列「{column}」含 {coerced_missing} 个非数值，无法{action}")
    return numeric


def dedupe(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """整行或按子集列去重；有重复时产出清洗数据集。"""
    subset = [
        str(column)
        for column in (params.get("columns") or step.target_columns or [])
        if column
    ]
    absent = [column for column in subset if column not in df.columns]
    if absent:
        raise ValueError(f"判重列包含不存在的列：{', '.join(absent)}")
    keep = str(params.get("keep", "first") or "first")
    if keep not in ("first", "last"):
        raise ValueError(f"keep 只支持 first/last，收到 {keep!r}")

    n_before = int(len(df))
    cleaned = df.drop_duplicates(subset=subset or None, keep=keep).reset_index(drop=True)
    duplicates = n_before - int(len(cleaned))

    result: dict[str, Any] = {
        "table": {
            "columns": ["n_before", "duplicates", "n_after", "keep", "subset"],
            "rows": [
                {
                    "n_before": n_before,
                    "duplicates": duplicates,
                    "n_after": int(len(cleaned)),
                    "keep": keep,
                    "subset": ", ".join(subset) or "（整行）",
                }
            ],
        },
    }
    if duplicates == 0:
        # 无重复不产出新数据集：避免向工作区倾倒无意义副本
        result["no_change"] = True
        return result
    name = "清洗数据集（去重）"
    emitted = _emit_cleaned(cleaned, params, name)
    if emitted:
        result.update(emitted)
    return result


def _condition_mask(series: pd.Series, op: str, value: Any) -> pd.Series:
    if op == "isna":
        return series.isna()
    if op == "notna":
        return series.notna()
    if op in ("eq", "ne"):
        return series == value if op == "eq" else series != value
    if op == "in":
        if not isinstance(value, list):
            raise ValueError(f"操作符 in 的 value 需为数组，收到 {value!r}")
        return series.isin(value)
    if op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"操作符 between 的 value 需为 [下界, 上界]，收到 {value!r}")
        return pd.to_numeric(series, errors="coerce").between(float(value[0]), float(value[1]))
    numeric = pd.to_numeric(series, errors="coerce")
    threshold = float(value)
    return {
        "gt": numeric > threshold,
        "ge": numeric >= threshold,
        "lt": numeric < threshold,
        "le": numeric <= threshold,
    }[op]


def filter_rows(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """按条件数组筛选行（多条件 AND）；产出清洗数据集。"""
    raw = params.get("conditions")
    if not isinstance(raw, list) or not raw:
        raise ValueError("筛选需要 conditions 数组：[{column, op, value}]")
    mask = pd.Series(True, index=df.index)
    readable: list[str] = []
    for position, condition in enumerate(raw, start=1):
        if not isinstance(condition, dict):
            raise ValueError(f"条件 {position} 需为对象（column/op/value）")
        column = str(condition.get("column", ""))
        op = str(condition.get("op", ""))
        if column not in df.columns:
            raise ValueError(f"条件 {position} 引用不存在的列：{column}")
        if op not in _FILTER_OPS:
            raise ValueError(f"条件 {position} 未知操作符：{op}（可选 {'/'.join(sorted(_FILTER_OPS))}）")
        mask &= _condition_mask(df[column], op, condition.get("value"))
        readable.append(f"{column} {op} {condition.get('value')!r}")

    n_before = int(len(df))
    filtered = df.loc[mask.fillna(False)].reset_index(drop=True)
    n_kept = int(len(filtered))
    if n_kept == 0:
        raise ValueError("筛选后剩余 0 行：请放宽条件（下游统计在空表上必然失败）")

    result: dict[str, Any] = {
        "table": {
            "columns": ["conditions", "n_before", "n_kept", "n_dropped"],
            "rows": [
                {
                    "conditions": "；".join(readable),
                    "n_before": n_before,
                    "n_kept": n_kept,
                    "n_dropped": n_before - n_kept,
                }
            ],
        },
    }
    emitted = _emit_cleaned(filtered, params, "清洗数据集（筛选）")
    if emitted:
        result.update(emitted)
    return result


def standardize(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """z-score / min-max 标准化（列内变换，列名不变）；产出清洗数据集。"""
    columns = [str(c) for c in (params.get("columns") or step.target_columns or [])]
    if not columns:
        raise ValueError("标准化需要至少 1 个目标列")
    method = str(params.get("method", "zscore") or "zscore")
    if method not in ("zscore", "minmax"):
        raise ValueError(f"未知标准化方法：{method}（可选 zscore/minmax）")

    out = df.copy()
    rows: list[dict[str, Any]] = []
    for column in columns:
        numeric = _numeric_series(df, column, "标准化")
        if int(numeric.notna().sum()) < 2:
            raise ValueError(f"列「{column}」有效数值不足 2 个，无法标准化")
        if method == "zscore":
            sd = float(numeric.std(ddof=1))
            if sd == 0:
                raise ValueError(f"列「{column}」标准差为 0，无法 z-score 标准化")
            out[column] = (numeric - numeric.mean()) / sd
            rows.append(
                {
                    "column": column,
                    "method": "zscore",
                    "mean_before": round(float(numeric.mean()), 6),
                    "sd_before": round(sd, 6),
                    "mean_after": round(float(out[column].mean()), 6),
                    "sd_after": round(float(out[column].std(ddof=1)), 6),
                }
            )
        else:
            minimum = float(numeric.min())
            span = float(numeric.max()) - minimum
            if span == 0:
                raise ValueError(f"列「{column}」极差为 0，无法 min-max 标准化")
            out[column] = (numeric - minimum) / span
            rows.append(
                {
                    "column": column,
                    "method": "minmax",
                    "min_before": round(minimum, 6),
                    "max_before": round(minimum + span, 6),
                    "min_after": round(float(out[column].min()), 6),
                    "max_after": round(float(out[column].max()), 6),
                }
            )

    result: dict[str, Any] = {"table": {"columns": list(rows[0].keys()), "rows": rows}}
    emitted = _emit_cleaned(out, params, "清洗数据集（标准化）")
    if emitted:
        result.update(emitted)
    return result


def bin_column(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """等频 / 等宽分箱：新增 {col}_bin 列，整数箱号 1..k；产出清洗数据集。"""
    columns = [str(c) for c in (step.target_columns or [])]
    if not columns:
        raise ValueError("分箱需要至少 1 个目标列")
    method = str(params.get("method", "quantile") or "quantile")
    if method not in ("quantile", "equal_width"):
        raise ValueError(f"未知分箱方法：{method}（可选 quantile/equal_width）")
    n_bins = int(params.get("bins", 4) or 4)
    if n_bins < 2:
        raise ValueError("分箱数至少为 2")
    output_name = str(params.get("output_column") or "")
    if output_name and len(columns) > 1:
        raise ValueError("output_column 仅支持单列分箱；多列请用默认 {col}_bin 命名")

    out = df.copy()
    rows: list[dict[str, Any]] = []
    for column in columns:
        numeric = _numeric_series(df, column, "分箱")
        if int(numeric.notna().sum()) < n_bins:
            raise ValueError(f"列「{column}」有效数值不足 {n_bins} 个，无法分 {n_bins} 箱")
        if method == "quantile":
            codes, edges = pd.qcut(
                numeric, n_bins, labels=False, retbins=True, duplicates="drop"
            )
        else:
            codes, edges = pd.cut(numeric, n_bins, labels=False, retbins=True)
        bins_actual = int(len(edges) - 1)
        name = output_name or f"{column}_bin"
        out[name] = pd.Series(codes, index=df.index) + 1
        rows.append(
            {
                "column": column,
                "output_column": name,
                "method": method,
                "bins_requested": n_bins,
                "bins_actual": bins_actual,
                "edges": [round(float(edge), 6) for edge in edges],
            }
        )

    result: dict[str, Any] = {"table": {"columns": list(rows[0].keys()), "rows": rows}}
    emitted = _emit_cleaned(out, params, "清洗数据集（分箱）")
    if emitted:
        result.update(emitted)
    return result


def outlier_report(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """异常值识别（报告型）：IQR 法（k 可调）或 z-score 3σ 法；不产数据集。"""
    columns = [str(c) for c in (step.target_columns or [])]
    if not columns:
        raise ValueError("异常值识别需要至少 1 个目标列")
    method = str(params.get("method", "iqr") or "iqr")
    if method not in ("iqr", "zscore"):
        raise ValueError(f"未知识别方法：{method}（可选 iqr/zscore）")

    rows: list[dict[str, Any]] = []
    for column in columns:
        numeric = _numeric_series(df, column, "识别异常值")
        n_valid = int(numeric.notna().sum())
        if n_valid < 4:
            raise ValueError(f"列「{column}」有效数值不足 4 个，无法识别异常值")
        if method == "iqr":
            k = float(params.get("k", 1.5) or 1.5)
            q1, q3 = numeric.quantile([0.25, 0.75])
            lower, upper = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
        else:
            sd = float(numeric.std(ddof=1))
            if sd == 0:
                raise ValueError(f"列「{column}」标准差为 0，无法用 z-score 识别")
            lower, upper = numeric.mean() - 3 * sd, numeric.mean() + 3 * sd
        outliers = int(((numeric < lower) | (numeric > upper)).sum())
        rows.append(
            {
                "column": column,
                "method": method,
                "lower": round(float(lower), 6),
                "upper": round(float(upper), 6),
                "outliers": outliers,
                "percent": round(outliers * 100.0 / n_valid, 4),
            }
        )

    return {"table": {"columns": list(rows[0].keys()), "rows": rows}}


def winsorize(df: pd.DataFrame, step: Any, params: dict) -> dict:
    """截尾：把界外值压到边界（IQR 法或百分位法）；产出清洗数据集。"""
    columns = [str(c) for c in (step.target_columns or [])]
    if not columns:
        raise ValueError("截尾需要至少 1 个目标列")
    method = str(params.get("method", "iqr") or "iqr")
    if method not in ("iqr", "percentile"):
        raise ValueError(f"未知截尾方法：{method}（可选 iqr/percentile）")

    out = df.copy()
    rows: list[dict[str, Any]] = []
    for column in columns:
        numeric = _numeric_series(df, column, "截尾")
        if int(numeric.notna().sum()) < 4:
            raise ValueError(f"列「{column}」有效数值不足 4 个，无法截尾")
        if method == "iqr":
            k = float(params.get("k", 1.5) or 1.5)
            q1, q3 = numeric.quantile([0.25, 0.75])
            lower, upper = q1 - k * (q3 - q1), q3 + k * (q3 - q1)
        else:
            lower_pct = float(params.get("lower_pct", 1) or 1)
            upper_pct = float(params.get("upper_pct", 99) or 99)
            if not (0 <= lower_pct < upper_pct <= 100):
                raise ValueError(f"百分位区间非法：{lower_pct}~{upper_pct}（需 0 ≤ 下 < 上 ≤ 100）")
            lower, upper = numeric.quantile([lower_pct / 100.0, upper_pct / 100.0])
        n_lower = int((numeric < lower).sum())
        n_upper = int((numeric > upper).sum())
        out[column] = numeric.clip(lower=float(lower), upper=float(upper))
        rows.append(
            {
                "column": column,
                "method": method,
                "lower": round(float(lower), 6),
                "upper": round(float(upper), 6),
                "n_capped_lower": n_lower,
                "n_capped_upper": n_upper,
            }
        )

    result: dict[str, Any] = {"table": {"columns": list(rows[0].keys()), "rows": rows}}
    emitted = _emit_cleaned(out, params, "清洗数据集（截尾）")
    if emitted:
        result.update(emitted)
    return result

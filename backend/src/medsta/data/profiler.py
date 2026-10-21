"""数据统计画像：DataFrame -> 可序列化的 TableProfile。

变量类型四槽位（用户可在画像中修正）：continuous（整数值-连续型）、
ordinal（数值-等级型）、categorical（类别型）、index（序列索引，统计默认排除）。
画像供讨论智能体使用（prompt info 输入），字段必须可 JSON 序列化。
"""
from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel

ColumnType = Literal[
    "continuous", "ordinal", "categorical", "index",
    "datetime", "boolean", "text",
]

COLUMN_TYPES: tuple[ColumnType, ...] = (
    "continuous", "ordinal", "categorical", "index", "datetime", "boolean", "text",
)

_ORDINAL_MAX_DISTINCT = 12
_CATEGORICAL_MAX_DISTINCT = 50

# 常见测量指标：整数值但语义连续（年龄/血压/身高…），不应按等级型降级非参数
# 英文必须按词元匹配（age 是 stage/percentage 的子串）；中文用子串匹配
_CONTINUOUS_NAME_HINTS_EN = frozenset(
    {
        "age", "height", "weight", "bmi", "bp", "sbp", "dbp", "hr",
        "temp", "temperature", "glucose", "cholesterol", "creatinine",
        "albumin", "hemoglobin", "hgb", "wbc", "platelet",
        "followup", "follow_up", "duration",
    }
)
_CONTINUOUS_NAME_HINTS_ZH = (
    "年龄", "身高", "体重", "血压", "收缩压", "舒张压", "体温", "心率",
    "血糖", "胆固醇", "肌酐", "白蛋白", "血红蛋白", "白细胞", "血小板",
    "随访", "病程", "时长",
)

VALID_COLUMN_TYPES = COLUMN_TYPES


def _looks_like_measurement(name: str) -> bool:
    """列名是否指向常见连续测量指标（而非评分/分级/计数）。"""
    if any(hint in name for hint in _CONTINUOUS_NAME_HINTS_ZH):
        return True
    tokens = set(re.split(r"[^a-z0-9]+", name.lower()))
    return bool(tokens & _CONTINUOUS_NAME_HINTS_EN)


class ColumnProfile(BaseModel):
    name: str
    type: ColumnType
    missing: int
    stats: dict[str, float | int | str | None]


class TableProfile(BaseModel):
    row_count: int
    column_count: int
    columns: dict[str, ColumnProfile]
    type_confirmed: bool = False


def _infer_column_type(series: pd.Series, name: str, position: int) -> ColumnType:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        non_null = series.dropna()
        # 索引样：唯一值=行数且单调（首列 0/1 起始的序号）；行数<5 不判索引（小样本防误判）
        if (
            len(series) >= 5
            and non_null.nunique() == len(non_null) == len(series)
            and (series.is_monotonic_increasing or series.is_monotonic_decreasing)
            and non_null.iloc[0] in (0, 1)
        ):
            return "index"
        # 小基数整数：测量指标按连续处理；评分/分级（非负且跨度小）仍判等级型
        if pd.api.types.is_integer_dtype(series) and non_null.nunique() <= _ORDINAL_MAX_DISTINCT:
            if non_null.empty:
                return "ordinal"
            if _looks_like_measurement(name):
                return "continuous"
            span = float(non_null.max() - non_null.min())
            if bool((non_null >= 0).all()) and span <= 10:
                return "ordinal"
            return "continuous"
        return "continuous"
    non_null = series.dropna().astype(str)
    if non_null.nunique() <= _CATEGORICAL_MAX_DISTINCT:
        return "categorical"
    return "text"


def _numeric_stats(series: pd.Series) -> dict[str, float | int | None]:
    """七列口径：计数/均值/中位数/q25/q75/最小/最大。"""
    values = series.dropna()
    if values.empty:
        return {"count": 0, "mean": None, "median": None,
                "q25": None, "q75": None, "min": None, "max": None}
    return {
        "count": int(values.count()),
        "mean": round(float(values.mean()), 4),
        "median": round(float(values.median()), 4),
        "q25": round(float(values.quantile(0.25)), 4),
        "q75": round(float(values.quantile(0.75)), 4),
        "min": round(float(values.min()), 4),
        "max": round(float(values.max()), 4),
    }


def _categorical_stats(series: pd.Series) -> dict[str, float | int | str | None]:
    non_null = series.dropna().astype(str)
    top = non_null.mode()
    return {
        "count": int(len(non_null)),
        "distinct": int(non_null.nunique()),
        "top": str(top.iloc[0]) if len(top) > 0 else None,
    }


def _column_stats(series: pd.Series, col_type: ColumnType) -> dict[str, Any]:
    if col_type in ("continuous", "ordinal"):
        return _numeric_stats(series)
    if col_type in ("categorical", "boolean"):
        return _categorical_stats(series)
    return {"count": int(series.notna().sum())}


def profile_dataframe(df: pd.DataFrame) -> TableProfile:
    """生成逐列画像（含变量类型建议）与整体汇总。"""
    columns: dict[str, ColumnProfile] = {}
    for position, (name, series) in enumerate(df.items()):
        col_type = _infer_column_type(series, str(name), position)
        columns[str(name)] = ColumnProfile(
            name=str(name),
            type=col_type,
            missing=int(series.isna().sum()),
            stats=_column_stats(series, col_type),
        )
    return TableProfile(
        row_count=int(len(df)),
        column_count=int(df.shape[1]),
        columns=columns,
    )


def apply_column_type(
    df: pd.DataFrame, profile: TableProfile, column: str, new_type: ColumnType
) -> TableProfile:
    """用户修正列类型：更新类型并按新类型重算该列统计。"""
    if column not in profile.columns:
        raise KeyError(f"列不存在：{column}")
    series = df[column]
    entry = profile.columns[column]
    entry.type = new_type
    entry.stats = _column_stats(series, new_type)
    return profile

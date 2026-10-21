"""019 B7：数据质检 —— 变量类型、七列口径、缺失报告与类型修正。"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.data.profiler import apply_column_type, profile_dataframe
from medsta.stats.methods import missing_report
from medsta.stats.registry import validate_step


def _quality_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "seq": [0, 1, 2, 3, 4, 5],
            "score": [1.5, 2.25, 3.0, np.nan, 5.5, 6.75],
            "likert": [1, 2, 3, 4, 5, 1],
            "city": ["a", "b", "a", "b", "c", "c"],
        }
    )


def test_inference_covers_four_slots() -> None:
    """B7: 四槽位推断：浮点→连续、小基数整数→等级、字符串→类别、0 起单调序号→索引。"""
    profile = profile_dataframe(_quality_df())

    types = {name: column.type for name, column in profile.columns.items()}
    assert types["score"] == "continuous"
    assert types["likert"] == "ordinal"
    assert types["city"] == "categorical"
    assert types["seq"] == "index"
    assert profile.type_confirmed is False


def test_integer_measurement_columns_are_continuous() -> None:
    """B1(020): 整数测量变量（年龄/血压）按名称识别为连续，避免降级非参数。"""
    df = pd.DataFrame(
        {
            "age": [25, 31, 42, 38, 51, 47, 29, 60, 33, 45, 52, 27],
            "年龄": [25, 31, 42, 38, 51, 47, 29, 60, 33, 45, 52, 27],
            "systolic_bp": [110, 120, 125, 118, 135, 128, 115, 140, 122, 130, 138, 124],
            "stage": [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4],
        }
    )

    types = {name: column.type for name, column in profile_dataframe(df).columns.items()}

    assert types["age"] == "continuous"
    assert types["年龄"] == "continuous"
    assert types["systolic_bp"] == "continuous"
    # 英文按词元匹配：stage 不应因包含 "age" 子串而被误判
    assert types["stage"] == "ordinal"


def test_small_range_integers_stay_ordinal_and_wide_counts_continuous() -> None:
    """B2(020): 非负且跨度≤10 的整数仍是等级型；宽范围整数计数视为连续。"""
    df = pd.DataFrame(
        {
            "likert": [1, 2, 3, 4, 5, 1, 2, 3],
            "grade": [3, 0, 5, 1, 6, 2, 4, 10],
            "visits": [3, 0, 7, 12, 20, 25, 31, 40],
        }
    )

    types = {name: column.type for name, column in profile_dataframe(df).columns.items()}

    assert types["likert"] == "ordinal"
    assert types["grade"] == "ordinal"
    assert types["visits"] == "continuous"


def test_binary_integers_remain_ordinal() -> None:
    """B3(020): 0/1 整数保持既有等级语义，不改动类型映射契约。"""
    df = pd.DataFrame({"response": [0, 1, 0, 1, 1, 0, 0, 1]})

    assert profile_dataframe(df).columns["response"].type == "ordinal"


def test_high_cardinality_strings_are_text_not_categorical() -> None:
    """B7: 高基数文本列不当作类别（避免把自由文本塞进卡方/频数表）。"""
    df = pd.DataFrame({"note": [f"note-{index}" for index in range(60)]})

    assert profile_dataframe(df).columns["note"].type == "text"


def test_continuous_stats_use_seven_key_contract() -> None:
    """B7: 连续列七列口径：count/mean/median/q25/q75/min/max，缺失不计入 count。"""
    profile = profile_dataframe(_quality_df())

    stats = profile.columns["score"].stats
    assert set(stats) == {"count", "mean", "median", "q25", "q75", "min", "max"}
    assert stats["count"] == 5
    assert stats["min"] == 1.5 and stats["max"] == 6.75
    assert profile.columns["score"].missing == 1


def test_index_column_is_rejected_by_statistics() -> None:
    """B7: 索引列默认不参与统计，返回可修复提示。"""
    profile = profile_dataframe(_quality_df())
    step = PlanStep(
        title="对序号做描述",
        method="describe",
        target_columns=["seq"],
        chart_type="none",
        params={},
        rationale="尝试分析序号列",
    )

    issues = validate_step(step, profile)

    assert [issue.code for issue in issues] == ["COLUMN_TYPE_MISMATCH"]
    assert "序列索引" in issues[0].message
    assert "改为连续型" in issues[0].hint


def test_missing_report_by_group() -> None:
    """B7: 缺失报告输出逐列缺失率与分组缺失数 + 完整病例数。"""
    df = pd.DataFrame(
        {
            "group": ["A", "A", "B", "B", "B"],
            "value": [1.0, np.nan, 3.0, np.nan, np.nan],
            "sex": ["F", "M", "F", "M", "F"],
        }
    )
    step = PlanStep(
        title="缺失报告",
        method="missing_report",
        target_columns=["value", "sex"],
        chart_type="none",
        params={"group_by": "group"},
        rationale="接入后先判断缺失机制",
    )

    result = missing_report(df, step, step.params)

    assert result["row_count"] == 5
    assert result["complete_rows"] == 2
    assert result["columns"]["value"]["missing"] == 3
    assert result["columns"]["value"]["missing_pct"] == 60.0
    assert result["columns"]["value"]["by_group"] == {"A": 1, "B": 2}
    assert result["columns"]["sex"]["missing"] == 0
    assert "MCAR" in result["note"] and "MNAR" in result["note"]


def test_apply_column_type_recomputes_stats() -> None:
    """B7: 用户修正类型后按新类型重算统计（数值↔类别口径切换）。"""
    df = _quality_df()
    profile = profile_dataframe(df)

    apply_column_type(df, profile, "likert", "categorical")
    stats = profile.columns["likert"].stats
    assert stats["distinct"] == 5
    assert "mean" not in stats

    apply_column_type(df, profile, "likert", "continuous")
    assert profile.columns["likert"].stats["mean"] == pytest.approx(2.6667, abs=1e-3)

    with pytest.raises(KeyError):
        apply_column_type(df, profile, "not_a_column", "continuous")


def test_profile_is_json_serializable() -> None:
    """B7: 画像可直接下发给前端/模型（不依赖 numpy 标量）。"""
    profile = profile_dataframe(_quality_df())

    payload = json.dumps(profile.model_dump(), ensure_ascii=False)

    assert "score" in payload
    assert profile.row_count == 6
    assert profile.column_count == 4

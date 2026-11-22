"""033 B1：JSON 输出硬门——registry 全部工具经 execute_step 出口可严格序列化。

用户硬要求：所有分析数据输出为 JSON。契约绑定在 registry.execute_step 单一出口，
未来新增工具不通过严格 JSON 检查无法合入（NaN/Inf/numpy 类型均为硬失败）。
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats.registry import execute_step


def _sample_df() -> pd.DataFrame:
    """覆盖全部工具族的最小合法样本：数值/分组/二分类/配对文本/生存/区组/析因/重复测量/时序。"""
    return pd.DataFrame(
        {
            "group": ["A"] * 8 + ["B"] * 8,
            "value": [10.0, 11.0, 9.0, 10.5, 10.2, 9.8, 10.3, 10.1,
                      12.0, 12.6, 11.4, 12.8, 12.2, 11.7, 12.35, 12.05],
            "value2": [5.1, 5.6, 4.7, 5.3, 5.2, 4.9, 5.4, 5.0,
                       6.1, 6.6, 5.7, 6.3, 6.2, 5.9, 6.4, 6.0],
            "outcome": [0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0],
            "paired_a": ["阳性"] * 8 + ["阴性"] * 8,
            "paired_b": ["阳性", "阳性", "阳性", "阳性", "阳性", "阳性", "阴性", "阴性",
                         "阳性", "阳性", "阳性", "阳性", "阴性", "阴性", "阴性", "阴性"],
            "time": [5.0, 8.0, 12.0, 3.0, 20.0, 7.0, 15.0, 9.0,
                     2.0, 6.0, 10.0, 4.0, 18.0, 8.0, 14.0, 6.0],
            "event": [1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1],
            "block": [1, 2, 3, 4] * 4,
            "factor_a": ["A", "B"] * 8,
            "factor_b": ["X"] * 8 + ["Y"] * 8,
            "subject": [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4],
            "within": [1, 2, 3, 4] * 4,
        }
    )


# 每工具最小合法输入：targets + 显式参数（choice 取首选项或默认）+ 可选行采样
_CASES: dict[str, tuple[list[str], dict, list[int] | None]] = {
    "describe": (["value"], {"group_by": "group"}, None),
    "descriptive_stats": (["value"], {}, None),
    "reference_range": (["value"], {"percentage": "95", "sides": "two", "method": "normal"}, None),
    "one_sample_test": (["value"], {"mu0": 10}, None),
    "missing_report": (["value", "value2"], {}, None),
    "impute": (["value"], {"columns": ["value"], "method": "median"}, None),
    # 数据清洗（045）：产物数据集路径为 str，其余为标准标量
    "dedupe": ([], {}, None),
    "filter_rows": ([], {"conditions": [{"column": "group", "op": "eq", "value": "A"}]}, None),
    "standardize": (["value"], {}, None),
    "bin_column": (["value"], {"bins": 3}, None),
    "outlier_report": (["value"], {}, None),
    "winsorize": (["value"], {}, None),
    "normality_test": (["value"], {}, None),
    "group_compare": (["value"], {"group_column": "group"}, None),
    "anova": (["value"], {"group_column": "group"}, None),
    # 随机区组要求每处理×区组单元恰 1 个观测：A/B 两组 × block 1..4 各取一行
    "randomized_block_anova": (
        ["value"], {"group_column": "group", "block_column": "block"},
        [0, 8, 1, 9, 2, 10, 3, 11],
    ),
    "chi_square": (["group", "outcome"], {"row_column": "group", "col_column": "outcome"}, None),
    "factorial_anova": (["value"], {"factor_a": "factor_a", "factor_b": "factor_b"}, None),
    "repeated_measures_anova": (["value"], {"subject_column": "subject", "within_column": "within"}, None),
    "mcnemar_test": (["paired_a", "paired_b"], {}, None),
    "survival_analysis": (["time"], {"time_col": "time", "event_col": "event", "group_col": "group"}, None),
    "sample_size": ([], {"design": "two_means", "solve": "n", "effect_size": 0.8}, None),
    "correlation": (["value", "value2"], {"method": "pearson"}, None),
    "regression": (["value"], {"target": "value", "features": ["value2"]}, None),
    "logistic_regression": (["outcome"], {"target": "outcome", "features": ["value"]}, None),
    "timeseries_forecast": (["value"], {"forecast_n": 3}, None),
    "levene_test": (["value"], {"group_column": "group"}, None),
    "aggregate_table": (["value"], {"group_column": "group", "agg": "mean"}, None),
}


def test_case_table_covers_every_registered_tool() -> None:
    """采样表必须覆盖注册表全部工具：新工具登记时必须同时登记 JSON 采样。"""
    from medsta.stats.registry import _REGISTRY

    assert set(_CASES) == set(_REGISTRY), (
        f"采样缺口：{set(_REGISTRY) - set(_CASES)}；多余：{set(_CASES) - set(_REGISTRY)}"
    )


@pytest.mark.parametrize("tool", sorted(_CASES))
def test_tool_output_is_strict_json(tool: str, tmp_path) -> None:
    """B1: 每个工具经 execute_step 出口的输出可 json.dumps(allow_nan=False)。"""
    targets, params, rows = _CASES[tool]
    step = PlanStep(
        title=f"{tool} 契约采样",
        method=tool,
        target_columns=targets,
        chart_type="none",
        params=dict(params),
        rationale="JSON 输出契约采样",
    )
    frame = _sample_df()
    if rows is not None:
        frame = frame.iloc[rows].reset_index(drop=True)

    result, _ = execute_step(frame, step, tmp_path, 0)

    text = json.dumps(result, allow_nan=False, ensure_ascii=False)
    assert isinstance(text, str) and len(text) > 2

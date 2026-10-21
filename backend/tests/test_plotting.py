"""019 B14：11 类图表产物契约、拼图、字体回退与显著性标注。"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from medsta.agents.discussion import PlanStep
from medsta.stats import plotting
from medsta.stats.registry import CHART_TYPES, get_tool


CHART_CASES = [
    ("histogram", "describe", ["value"], {}),
    ("boxplot", "group_compare", ["value"], {"group_column": "group"}),
    ("violin", "group_compare", ["value"], {"group_column": "group"}),
    ("scatter", "correlation", ["value", "age"], {}),
    ("line", "timeseries_forecast", ["visit"], {"forecast_n": 3}),
    ("bar", "aggregate_table", ["value"], {"group_column": "group", "agg": "mean"}),
    ("grouped_bar", "aggregate_table", ["value"], {"group_column": "group", "agg": "mean"}),
    ("heatmap", "correlation", ["value", "age"], {}),
    ("qq_plot", "normality_test", ["value"], {}),
    ("residual_plot", "regression", ["value"], {"target": "value", "features": ["age"]}),
    ("pie", "describe", ["group"], {}),
]


def _step(chart: str, method: str, targets: list[str], params: dict) -> PlanStep:
    return PlanStep(
        title=f"{method} 的 {chart} 图",
        method=method,
        target_columns=targets,
        chart_type=chart,
        params=dict(params),
        rationale="图表产物契约测试",
    )


def test_chart_catalog_covers_all_rendered_types() -> None:
    """B14: 能力目录图表清单与渲染实现一致（含 pie）。"""
    rendered = {name for name, *_ in CHART_CASES}

    assert rendered <= set(CHART_TYPES)
    assert set(CHART_TYPES) - {"none"} == rendered


def test_every_chart_type_renders_valid_png(sample_df, tmp_path) -> None:
    """B14: 11 类图表均产出可用的 PNG（文件名含类型、>1KB、无缺字警告）。"""
    for index, (chart, method, targets, params) in enumerate(CHART_CASES):
        step = _step(chart, method, targets, params)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            path = plotting.render_chart(sample_df, step, tmp_path, index)

        assert path.is_file(), chart
        assert path.name.endswith(f"_{chart}.png"), path.name
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert path.stat().st_size > 1024, chart
        glyph = [item for item in caught if "missing from font" in str(item.message)]
        assert glyph == [], f"{chart}: {glyph}"


def test_chart_title_falls_back_to_english_without_cjk_font() -> None:
    """B14: 无 CJK 字体时标题回退英文，避免缺字与乱码。"""
    step = _step("histogram", "describe", ["value"], {})
    title = plotting.chart_title(step, 0)

    if plotting.CJK_FONT:
        assert title == "describe 的 histogram 图"
    else:
        assert title == "histogram · step 1"


def test_boxplot_annotates_pairwise_significance(sample_df, tmp_path) -> None:
    """B14: 组间比较图可标注校正后星号（不遮挡、不崩溃）。"""
    step = _step("boxplot", "group_compare", ["value"], {"group_column": "group"})
    result = {
        "p_value": 0.001,
        "pairwise": {
            "rows": [
                {"group_a": "A", "group_b": "B", "adjusted_p": 0.0001},
                {"group_a": "B", "group_b": "C", "adjusted_p": 0.02},
                {"group_a": "A", "group_b": "C", "adjusted_p": 0.4},
            ]
        },
    }

    path = plotting.render_chart(sample_df, step, tmp_path, 0, result=result)

    assert path.is_file()
    assert path.stat().st_size > 1024


def test_render_combined_builds_single_canvas(sample_df, tmp_path) -> None:
    """B14: 多图同画板输出 charts_combined.png，尺寸大于单图。"""
    first = plotting.render_chart(
        sample_df, _step("histogram", "describe", ["value"], {}), tmp_path, 0
    )
    second = plotting.render_chart(
        sample_df, _step("boxplot", "group_compare", ["value"], {"group_column": "group"}),
        tmp_path, 1,
    )

    combined = plotting.render_combined([first, second], tmp_path)

    assert combined.name == "charts_combined.png"
    assert combined.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert combined.stat().st_size > max(first.stat().st_size, second.stat().st_size)


def test_unknown_chart_and_missing_group_are_rejected(sample_df, tmp_path) -> None:
    """B14: 未知图表/缺分组参数显式报错，而不是画出空图。"""
    from types import SimpleNamespace

    bogus = SimpleNamespace(
        title="未知图",
        method="describe",
        target_columns=["value"],
        chart_type="sunburst",
        params={},
    )
    with pytest.raises(ValueError, match="未知图表类型"):
        plotting.render_chart(sample_df, bogus, tmp_path, 0)

    with pytest.raises(ValueError, match="grouped_bar"):
        plotting.render_chart(
            sample_df, _step("grouped_bar", "describe", ["value"], {}), tmp_path, 0
        )


def test_default_chart_mapping_by_column_type() -> None:
    """B14: 类型驱动默认图表：索引→折线、类别/等级→柱状、连续→直方图。"""
    assert plotting.default_chart_for("index") == "line"
    assert plotting.default_chart_for("categorical") == "bar"
    assert plotting.default_chart_for("ordinal") == "bar"
    assert plotting.default_chart_for("continuous") == "histogram"
    assert plotting.default_chart_for("continuous", "timeseries_forecast") == "line"


def test_summarize_series_uses_numeric_and_categorical_contracts() -> None:
    """B14: 数值摘要七列；类别摘要 distinct/top/ratio。"""
    numeric = plotting.summarize_series(pd.Series([1.0, 2.0, 3.0, np.nan]))
    categorical = plotting.summarize_series(pd.Series(["a", "a", "b"]))

    assert numeric["count"] == 3 and numeric["mean"] == 2.0
    assert categorical["distinct"] == 2
    assert categorical["top"] == "a"
    assert categorical["ratio"] == pytest.approx(0.6667, abs=1e-3)


def test_cohens_d_direction_and_scale() -> None:
    """B14: Cohen's d 方向随均值差，等方差数据量级为均值差/合并标准差。"""
    assert plotting.cohens_d(np.array([1.0, 2.0, 3.0]), np.array([2.0, 3.0, 4.0])) == pytest.approx(-1.0)
    assert plotting.cohens_d(np.array([1.0]), np.array([2.0])) == 0.0


def test_every_registered_tool_chart_is_renderable_or_declared() -> None:
    """B14: 注册表声明的图表都在能力清单中，避免前端下拉出现无法渲染的选项。"""
    for method in ("describe", "group_compare", "anova", "correlation", "regression"):
        spec = get_tool(method)
        assert spec is not None
        unknown = set(spec.charts) - set(CHART_TYPES) - {"none"}
        assert unknown == set(), f"{method}: {unknown}"

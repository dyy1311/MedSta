"""图表渲染：中文字体配置 + 10 类图表。

字体策略：优先系统 CJK 字体（Noto Serif/Sans CJK、WenQuanYi、SimHei）；
无 CJK 字体时标题回退英文，避免 "Glyph missing" 警告与乱码。
"""
from __future__ import annotations

import pathlib
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_CJK_CANDIDATES = (
    "Noto Serif CJK SC",
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "SimHei",
    "Microsoft YaHei",
)

CHART_LABELS = {
    "histogram": "histogram",
    "boxplot": "boxplot",
    "violin": "violin",
    "scatter": "scatter",
    "line": "line",
    "bar": "bar",
    "grouped_bar": "grouped bar",
    "heatmap": "heatmap",
    "qq_plot": "Q-Q plot",
    "residual_plot": "residual plot",
    "pie": "pie",
    "survival_curve": "survival curve",
}


def _stars(p_value: float | None) -> str:
    if p_value is None:
        return "ns"
    return "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else "ns"


def _annotate_pairwise(ax, positions: list[str], pairs: list[dict], alpha: float) -> None:
    """在组间绘制比较线并标注星号/ns（最多 3 对，按校正后 p 升序）。"""

    ymax = ax.get_ylim()[1]
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    level = 0
    ranked = sorted(pairs, key=lambda row: row.get("adjusted_p", row.get("p_value", 1.0)))
    for row in ranked[:3]:
        try:
            i, j = positions.index(row["group_a"]), positions.index(row["group_b"])
        except (ValueError, KeyError):
            continue
        y = ymax + span * (0.05 + level * 0.12)
        ax.plot([i, i, j, j], [y - span * 0.02, y, y, y - span * 0.02], lw=1, color="#495057")
        p_value = row.get("adjusted_p", row.get("p_value"))
        label = _stars(p_value) if p_value is not None else "ns"
        ax.text((i + j) / 2, y, label, ha="center", va="bottom", fontsize=9, color="#495057")
        level += 1
    ax.set_ylim(top=ymax + span * (0.15 + level * 0.12))


def _detect_cjk_font() -> str | None:
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_CANDIDATES:
        if name in available:
            return name
    return None


CJK_FONT = _detect_cjk_font()
if CJK_FONT:
    matplotlib.rcParams["font.sans-serif"] = [CJK_FONT, "DejaVu Sans"]
    matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["axes.unicode_minus"] = False


def chart_title(step: Any, index: int) -> str:
    """有 CJK 字体时用步骤标题，否则用英文回退，杜绝缺字警告。"""
    if CJK_FONT:
        return str(step.title)
    return f"{CHART_LABELS.get(step.chart_type, step.chart_type)} · step {index + 1}"


# 用户出图标注：内部保留键，与 _layout / _artifact_dir 同口径，模型不可填
PLOT_STYLE_KEYS = (
    ("title", "_plot_title"),
    ("xlabel", "_plot_xlabel"),
    ("ylabel", "_plot_ylabel"),
    ("xticks", "_plot_xticks"),
    ("yticks", "_plot_yticks"),
    ("groups", "_plot_groups"),
    ("group_order", "_plot_group_order"),
)


def style_from_params(params: dict | None) -> dict[str, str]:
    """从步骤 params 抽出非空标注，供报告回传前端回填。"""
    source = params or {}
    style: dict[str, str] = {}
    for public, internal in PLOT_STYLE_KEYS:
        text = str(source.get(internal) or "").strip()
        if text:
            style[public] = text
    return style


def merge_plot_style(params: dict, payload: dict) -> None:
    """把前端标注写入步骤 params；空字符串表示改回自动标注。"""
    for public, internal in PLOT_STYLE_KEYS:
        if public not in payload:
            continue
        text = str(payload.get(public) or "").strip()
        if text:
            params[internal] = text
        else:
            params.pop(internal, None)


def _parse_tick_spec(raw: str) -> tuple[list[float] | None, list[str]]:
    """逗号分隔：全是数字则作为刻度位置，否则作为刻度标签。"""
    labels = [part.strip() for part in raw.split(",") if part.strip()]
    if not labels:
        return None, []
    try:
        return [float(item) for item in labels], labels
    except ValueError:
        return None, labels


def _parse_group_spec(raw: str) -> tuple[dict[str, str], list[str]]:
    """组名：`原名=新名` 映射，或逗号分隔按出现顺序替换。"""
    mapping: dict[str, str] = {}
    ordered: list[str] = []
    for part in [item.strip() for item in raw.split(",") if item.strip()]:
        if "=" in part:
            old, new = part.split("=", 1)
            old, new = old.strip(), new.strip()
            if old and new:
                mapping[old] = new
        else:
            ordered.append(part)
    return mapping, ordered


def _order_names(names: list[str], order_spec: str, rename_spec: str = "") -> list[str]:
    """按用户指定重排列组；可用原名或已改的显示名。未点名的组保持相对顺序接在后面。"""
    wanted = [part.strip() for part in order_spec.split(",") if part.strip()]
    if not wanted:
        return names
    mapping, _ = _parse_group_spec(rename_spec)
    inverse = {new: old for old, new in mapping.items()}
    present = set(names)
    rank: dict[str, int] = {}
    for index, token in enumerate(wanted):
        key = token if token in present else inverse.get(token)
        if key in present and key not in rank:
            rank[key] = index
    listed = [name for name in names if name in rank]
    listed.sort(key=lambda name: rank[name])
    rest = [name for name in names if name not in rank]
    return listed + rest


# 组名出现在横轴上的图；生存曲线组名在图例，时间轴不动
_GROUP_TICK_CHARTS = {"boxplot", "violin", "bar", "grouped_bar"}


def _apply_group_names(axes: list[Any], spec: str, *, chart: str, faceted: bool) -> None:
    """改组标签：刻度、图例、饼图扇区、分面标题。成对比较线按原组位置绘制，不受显示名影响。"""
    mapping, ordered = _parse_group_spec(spec)
    if not mapping and not ordered:
        return
    live = [item for item in axes if item is not None]
    rename_ticks = chart in _GROUP_TICK_CHARTS
    for ax in live:
        if chart == "pie":
            slices = [text for text in ax.texts if "%" not in (text.get_text() or "")]
            if mapping:
                for text in slices:
                    text.set_text(mapping.get(text.get_text(), text.get_text()))
            else:
                for index, text in enumerate(slices):
                    if index < len(ordered):
                        text.set_text(ordered[index])
            continue
        ticks = [tick.get_text() for tick in ax.get_xticklabels()]
        legend = ax.get_legend()
        legend_texts = list(legend.get_texts()) if legend is not None else []
        legend_names = [item.get_text() for item in legend_texts]
        if mapping:
            if rename_ticks and ticks:
                ax.set_xticklabels([mapping.get(name, name) for name in ticks])
            for item in legend_texts:
                item.set_text(mapping.get(item.get_text(), item.get_text()))
        elif ordered:
            if chart == "survival_curve" and legend_texts:
                for index, item in enumerate(legend_texts):
                    if index < len(ordered):
                        item.set_text(ordered[index])
            elif rename_ticks and ticks:
                old_ticks = list(ticks)
                ax.set_xticklabels(
                    [ordered[index] if index < len(ordered) else name for index, name in enumerate(ticks)]
                )
                if legend_names == old_ticks:
                    for index, item in enumerate(legend_texts):
                        if index < len(ordered):
                            item.set_text(ordered[index])
        if faceted:
            title = ax.get_title()
            if " = " in title:
                prefix, value = title.rsplit(" = ", 1)
                if mapping:
                    ax.set_title(f"{prefix} = {mapping.get(value, value)}")
                elif ordered:
                    position = live.index(ax)
                    if position < len(ordered):
                        ax.set_title(f"{prefix} = {ordered[position]}")


def _apply_ticks(ax: Any, raw: str, which: str) -> None:
    locations, labels = _parse_tick_spec(raw)
    if not labels:
        return
    if which == "x":
        if locations is not None:
            ax.set_xticks(locations)
        else:
            ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
        return
    if locations is not None:
        ax.set_yticks(locations)
    else:
        ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)


def apply_plot_style(
    fig: Any,
    axes: list[Any],
    step: Any,
    index: int,
    *,
    faceted: bool,
    chart: str,
) -> None:
    """在默认出图之后覆盖标题/坐标轴；未填的字段保持数据驱动默认值。"""
    params = dict(step.params or {})
    title = str(params.get("_plot_title") or "").strip()
    xlabel = str(params.get("_plot_xlabel") or "").strip()
    ylabel = str(params.get("_plot_ylabel") or "").strip()
    xticks = str(params.get("_plot_xticks") or "").strip()
    yticks = str(params.get("_plot_yticks") or "").strip()
    groups = str(params.get("_plot_groups") or "").strip()
    live = [item for item in axes if item is not None]
    if title:
        if faceted or len(live) > 1:
            fig.suptitle(title)
        elif live:
            live[0].set_title(title)
    elif faceted:
        fig.suptitle(chart_title(step, index))
    elif live:
        live[0].set_title(chart_title(step, index))
    if groups:
        fig.canvas.draw()
        _apply_group_names(live, groups, chart=chart, faceted=faceted)
    if chart == "pie":
        return
    for item in live:
        if xlabel:
            item.set_xlabel(xlabel)
        if ylabel:
            item.set_ylabel(ylabel)
        if xticks:
            _apply_ticks(item, xticks, "x")
        if yticks:
            _apply_ticks(item, yticks, "y")


def render_chart(
    df: pd.DataFrame,
    step: Any,
    artifact_dir: pathlib.Path,
    index: int,
    result: Any = None,
    image_format: str = "png",
) -> pathlib.Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    columns = list(step.target_columns)
    chart = step.chart_type
    params = dict(step.params or {})
    faceted = False
    order_spec = str(params.get("_plot_group_order") or "").strip()
    rename_spec = str(params.get("_plot_groups") or "").strip()

    def order_of(names: list[str]) -> list[str]:
        return _order_names(names, order_spec, rename_spec) if order_spec else names

    if chart == "histogram":
        series = pd.to_numeric(df[columns[0]], errors="coerce").dropna()
        group_col = params.get("group_by")
        if group_col and group_col in df.columns:
            # 按类别分面：每个类别一个子图（用户要求「每个类别做一张图」）。
            # 组数过多时分面不可读，超过 6 组退回总体直方图。
            groups = [
                (str(key), pd.to_numeric(frame[columns[0]], errors="coerce").dropna())
                for key, frame in df.groupby(group_col, sort=False)
            ]
            groups = [(key, values) for key, values in groups if len(values)]
            keyed = dict(groups)
            groups = [(key, keyed[key]) for key in order_of([key for key, _ in groups])]
            if 1 < len(groups) <= 6:
                plt.close(fig)
                columns_n = 2 if len(groups) > 1 else 1
                rows_n = (len(groups) + columns_n - 1) // columns_n
                fig, axes = plt.subplots(
                    rows_n, columns_n, figsize=(6.4 * columns_n, 3.2 * rows_n), squeeze=False
                )
                low, high = float(series.min()), float(series.max())
                bins: Any = np.linspace(low, high, 16) if np.isfinite(high) else 15
                for position, (key, values) in enumerate(groups):
                    panel = axes[position // columns_n][position % columns_n]
                    panel.hist(values, bins=bins, color="#3B5BDB", alpha=0.85, edgecolor="white")
                    panel.set_title(f"{group_col} = {key}", fontsize=9)
                    panel.set_ylabel("count")
                for rest in range(len(groups), rows_n * columns_n):
                    axes[rest // columns_n][rest % columns_n].axis("off")
                fig.suptitle(f"{columns[0]} 按 {group_col} 分面（n={len(groups)} 组）", fontsize=10)
                ax = axes[0][0]
                faceted = True
        if not faceted:
            ax.hist(series, bins=15, color="#3B5BDB", alpha=0.85, edgecolor="white")
            ax.set_xlabel(columns[0])
            ax.set_ylabel("count")
    elif chart == "pie":
        series = df[columns[0]].dropna().astype(str)
        counts = series.value_counts()
        counts.index = [str(key) for key in counts.index]
        counts = counts.reindex(order_of(list(counts.index)))
        # tab20 有 20 色；超过 6 类时旧调色板会被截断，相邻扇区撞色
        pie_cmap = plt.colormaps["tab20"]
        colors = [pie_cmap(i % pie_cmap.N) for i in range(len(counts))]
        ax.pie(
            counts.values,
            labels=[str(k) for k in counts.index],
            autopct="%1.1f%%",
            colors=colors,
        )
    elif chart in ("boxplot", "violin"):
        group_col = params.get("group_column") or params.get("group_by")
        if group_col:
            pairs = [
                (str(key), pd.to_numeric(frame[columns[0]], errors="coerce").dropna())
                for key, frame in df.groupby(group_col, sort=False)
            ]
            keyed = dict(pairs)
            labels = order_of([key for key, _ in pairs])
            groups = [keyed[key] for key in labels]
        else:
            groups = [pd.to_numeric(df[c], errors="coerce").dropna() for c in columns]
            labels = columns
        if chart == "boxplot":
            ax.boxplot(groups, tick_labels=labels)
        else:
            ax.violinplot(groups, showmeans=True)
            ax.set_xticks(range(1, len(labels) + 1), labels)
        ax.set_ylabel(columns[0])
        if result is not None and group_col and len(labels) >= 2:
            alpha = float(params.get("alpha", 0.05))
            if "pairwise" in result:
                _annotate_pairwise(ax, labels, result["pairwise"]["rows"], alpha)
            elif result.get("p_value") is not None and len(labels) == 2:
                _annotate_pairwise(
                    ax,
                    labels,
                    [{"group_a": labels[0], "group_b": labels[1], "p_value": result["p_value"]}],
                    alpha,
                )
    elif chart == "scatter":
        if len(columns) >= 2:
            x, y = columns[0], columns[1]
            ax.scatter(df[x], df[y], alpha=0.75, color="#3B5BDB")
            ax.set_xlabel(x)
            ax.set_ylabel(y)
        else:
            ax.scatter(df[columns[0]], df.index, alpha=0.75, color="#3B5BDB")
    elif chart == "line":
        series = pd.to_numeric(df[columns[0]], errors="coerce")
        ax.plot(series.to_numpy(), marker="o", markersize=3, color="#3B5BDB")
        if step.method == "timeseries_forecast":
            forecast = params.get("_forecast_values")
            if forecast:
                offset = len(series)
                ax.plot(
                    range(offset, offset + len(forecast)),
                    forecast,
                    linestyle="--",
                    color="#E8590C",
                    label="forecast",
                )
                ax.legend()
        ax.set_xlabel("index")
        ax.set_ylabel(columns[0])
    elif chart == "survival_curve":
        payload = result or {}
        curves: list[tuple[str, list]] = []
        if isinstance(payload.get("groups"), dict):
            curves = [
                (str(label), group.get("points") or [])
                for label, group in payload["groups"].items()
            ]
            keyed_curves = dict(curves)
            curves = [(key, keyed_curves[key]) for key in order_of([key for key, _ in curves])]
        elif payload.get("points"):
            curves = [("overall", payload["points"])]
        palette = ["#3B5BDB", "#E8590C", "#2F9E44", "#9775FA", "#F08C00", "#22B8CF"]
        for offset, (label, points) in enumerate(curves):
            if not points:
                continue
            color = palette[offset % len(palette)]
            step_times = [0.0] + [float(point["time"]) for point in points]
            step_values = [1.0] + [float(point["survival"]) for point in points]
            ax.step(step_times, step_values, where="post", color=color, label=label)
            censored = [
                (float(point["time"]), float(point["survival"]))
                for point in points
                if point.get("censored")
            ]
            if censored:
                ax.plot(
                    [item[0] for item in censored],
                    [item[1] for item in censored],
                    linestyle="none",
                    marker="|",
                    markersize=8,
                    color=color,
                )
        ax.set_xlabel(str(payload.get("time_column") or "time"))
        ax.set_ylabel("survival")
        ax.set_ylim(0, 1.05)
        if len(curves) > 1:
            ax.legend()
    elif chart == "bar":
        group_col = params.get("group_column")
        if group_col:
            means = df.groupby(group_col, sort=False)[columns[0]].apply(
                lambda s: pd.to_numeric(s, errors="coerce").mean()
            )
            means.index = [str(key) for key in means.index]
            means = means.reindex(order_of(list(means.index)))
            ax.bar(list(means.index), means.to_numpy(), color="#3B5BDB")
            ax.set_ylabel(f"mean {columns[0]}")
        else:
            ax.bar(range(len(df)), pd.to_numeric(df[columns[0]], errors="coerce"))
            ax.set_xlabel("index")
            ax.set_ylabel(columns[0])
    elif chart == "grouped_bar":
        group_col = params.get("group_column") or params.get("group_by")
        contingency_methods = {"chi_square", "mcnemar_test"}
        if step.method in contingency_methods:
            # 列联表计数柱状图（修复：此前误用数值均值路径，分类数据画成空/错图）
            rows = ((result or {}).get("table") or {}).get("rows") or []
            if not rows:
                raise ValueError("列联表计数图需要检验结果中的列联表")
            category_key = next(iter(rows[0]))
            categories = order_of([str(row[category_key]) for row in rows])
            by_category = {str(row[category_key]): row for row in rows}
            rows = [by_category[name] for name in categories]
            series_names = order_of([str(key) for key in rows[0] if key != category_key])
            positions = np.arange(len(categories))
            width = 0.8 / max(1, len(series_names))
            palette = ["#3B5BDB", "#22B8CF", "#F08C00", "#2F9E44", "#9775FA"]
            for offset, name in enumerate(series_names):
                values = [float(row.get(name, 0) or 0) for row in rows]
                ax.bar(
                    positions + offset * width - 0.4 + width / 2,
                    values,
                    width,
                    label=str(name),
                    color=palette[offset % len(palette)],
                )
            ax.set_xticks(positions)
            ax.set_xticklabels(categories)
            ax.set_ylabel("频数")
            ax.legend(title=category_key)
        else:
            # 数值列：分组均值柱状图
            if not group_col:
                raise ValueError("grouped_bar 需要 group_column 参数")
            pivoted = df.groupby(group_col, sort=False)[columns].apply(
                lambda g: g.apply(pd.to_numeric, errors="coerce").mean()
            )
            pivoted.index = [str(key) for key in pivoted.index]
            pivoted = pivoted.reindex(order_of(list(pivoted.index)))
            col_names = [str(col) for col in pivoted.columns]
            pivoted = pivoted.reindex(columns=order_of(col_names))
            pivoted.plot(kind="bar", ax=ax, color=["#3B5BDB", "#22B8CF", "#F08C00", "#2F9E44"])
    elif chart == "heatmap":
        matrix = df[columns].apply(pd.to_numeric, errors="coerce").corr()
        image = ax.imshow(matrix, cmap="coolwarm", vmin=-1, vmax=1)
        fig.colorbar(image, ax=ax)
        ax.set_xticks(range(len(columns)), columns, rotation=45, ha="right")
        ax.set_yticks(range(len(columns)), columns)
    elif chart == "qq_plot":
        from scipy import stats as sp_stats

        series = pd.to_numeric(df[columns[0]], errors="coerce").dropna()
        if len(series) >= 3:
            sp_stats.probplot(series, dist="norm", plot=ax)
            ax.get_lines()[0].set_markerfacecolor("#3B5BDB")
            ax.get_lines()[0].set_markeredgecolor("#3B5BDB")
        ax.set_title(ax.get_title() or "Q-Q")
    elif chart == "residual_plot":
        import statsmodels.api as sm

        target = params["target"]
        features = list(params["features"])
        y = pd.to_numeric(df[target], errors="coerce")
        x = df[features].apply(pd.to_numeric, errors="coerce")
        model = sm.OLS(y.astype(float), sm.add_constant(x.astype(float))).fit()
        ax.scatter(model.fittedvalues, model.resid, alpha=0.75, color="#3B5BDB")
        ax.axhline(0, linestyle="--", color="#E03131")
        ax.set_xlabel("fitted")
        ax.set_ylabel("residual")
    else:
        raise ValueError(f"未知图表类型：{chart}")

    style_axes = list(fig.axes) if faceted else [ax]
    apply_plot_style(fig, style_axes, step, index, faceted=faceted, chart=chart)
    fig.tight_layout()
    suffix = "jpg" if image_format == "jpg" else image_format
    path = artifact_dir / f"step_{index}_{step.method}_{chart}.{suffix}"
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def summarize_series(series: pd.Series) -> dict[str, Any]:
    """数值/类别列统一摘要；数值口径：均值/中位数/q25/q75/最大/最小/计数。"""
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == series.notna().sum() and numeric.notna().any():
        values = numeric.dropna()
        return {
            "n": int(values.count()),
            "count": int(values.count()),
            "mean": round(float(values.mean()), 4),
            "median": round(float(values.median()), 4),
            "q25": round(float(values.quantile(0.25)), 4),
            "q75": round(float(values.quantile(0.75)), 4),
            "min": round(float(values.min()), 4),
            "max": round(float(values.max()), 4),
        }
    counts = series.dropna().astype(str).value_counts()
    total = int(counts.sum())
    return {
        "n": total,
        "count": total,
        "distinct": int(counts.size),
        "top": counts.index[0] if counts.size else None,
        "top_count": int(counts.iloc[0]) if counts.size else 0,
        "ratio": round(counts.iloc[0] / total, 4) if total else 0.0,
    }


def default_chart_for(column_type: str, method: str = "") -> str:
    """按变量类型给出默认图表建议。"""
    if method == "survival_analysis":
        return "survival_curve"
    if column_type == "index":
        return "line"
    if column_type == "categorical":
        return "bar"
    if column_type == "ordinal":
        return "bar"
    if method == "timeseries_forecast":
        return "line"
    return "histogram"


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    n1, n2 = len(a), len(b)
    if n1 < 2 or n2 < 2:
        return 0.0
    pooled = np.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
    return float((a.mean() - b.mean()) / pooled) if pooled else 0.0


def render_combined(paths: list[pathlib.Path], artifact_dir: pathlib.Path) -> pathlib.Path:
    """多图同画板：将已生成的 PNG 拼接为一张图。"""
    import math

    if len(paths) < 2:
        raise ValueError("拼接图至少需要 2 张已生成的图")
    rows = math.ceil(len(paths) / 2)
    fig, axes = plt.subplots(rows, 2, figsize=(6.4 * 2, 4.2 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax, path in zip(axes, paths):
        ax.imshow(plt.imread(path))
        ax.axis("off")
    for ax in axes[len(paths):]:
        ax.axis("off")
    fig.tight_layout()
    out = artifact_dir / "charts_combined.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out

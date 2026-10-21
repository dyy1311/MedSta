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
}


def _stars(p_value: float | None) -> str:
    if p_value is None:
        return "ns"
    return "***" if p_value < 0.001 else "**" if p_value < 0.01 else "*" if p_value < 0.05 else "ns"


def _annotate_pairwise(ax, positions: list[float], pairs: list[dict], alpha: float) -> None:
    """在组间绘制比较线并标注星号/ns（最多 3 对，按校正后 p 升序）。"""
    import itertools

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


def render_chart(
    df: pd.DataFrame, step: Any, artifact_dir: pathlib.Path, index: int, result: Any = None
) -> pathlib.Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    columns = list(step.target_columns)
    chart = step.chart_type
    params = dict(step.params or {})

    if chart == "histogram":
        series = pd.to_numeric(df[columns[0]], errors="coerce").dropna()
        ax.hist(series, bins=15, color="#3B5BDB", alpha=0.85, edgecolor="white")
        ax.set_xlabel(columns[0])
        ax.set_ylabel("count")
    elif chart == "pie":
        series = df[columns[0]].dropna().astype(str)
        counts = series.value_counts()
        ax.pie(
            counts.values,
            labels=[str(k) for k in counts.index],
            autopct="%1.1f%%",
            colors=["#3B5BDB", "#22B8CF", "#F08C00", "#2F9E44", "#E03131", "#9775FA"][: len(counts)],
        )
    elif chart in ("boxplot", "violin"):
        group_col = params.get("group_column") or params.get("group_by")
        if group_col:
            groups = [
                pd.to_numeric(g[columns[0]], errors="coerce").dropna()
                for _, g in df.groupby(group_col, sort=False)
            ]
            labels = [str(k) for k, _ in df.groupby(group_col, sort=False)]
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
    elif chart == "bar":
        group_col = params.get("group_column")
        if group_col:
            means = df.groupby(group_col, sort=False)[columns[0]].apply(
                lambda s: pd.to_numeric(s, errors="coerce").mean()
            )
            ax.bar([str(i) for i in means.index], means.to_numpy(), color="#3B5BDB")
            ax.set_ylabel(f"mean {columns[0]}")
        else:
            ax.bar(range(len(df)), pd.to_numeric(df[columns[0]], errors="coerce"))
            ax.set_xlabel("index")
            ax.set_ylabel(columns[0])
    elif chart == "grouped_bar":
        group_col = params.get("group_column") or params.get("group_by")
        if not group_col:
            raise ValueError("grouped_bar 需要 group_column 参数")
        pivoted = df.groupby(group_col, sort=False)[columns].apply(
            lambda g: g.apply(pd.to_numeric, errors="coerce").mean()
        )
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

    ax.set_title(chart_title(step, index))
    fig.tight_layout()
    path = artifact_dir / f"step_{index}_{step.method}_{chart}.png"
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

"""统计工具注册表：模型提示、前端披露、宿主校验、执行派发的唯一真相源。

ToolSpec 决定「方法能做什么、需要什么参数、能画什么图」；
PlanStep 只携带模型的选择，宿主在此校验后才执行——缺参不会走到实现体，
从而消除 KeyError 类崩溃。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import pandas as pd
from pydantic import BaseModel

from medsta.errors import ErrorCode
from medsta.stats import methods
from medsta.stats.plotting import render_chart

CHART_TYPES = (
    "histogram", "boxplot", "violin", "scatter", "line",
    "bar", "grouped_bar", "pie", "heatmap", "qq_plot", "residual_plot", "none",
)


class ToolIssue(BaseModel):
    """结构化校验问题：code 用于前端分类，hint 用于修复建议。"""

    code: str
    message: str
    hint: str = ""
    step_index: int | None = None


@dataclass(frozen=True)
class ToolParam:
    name: str
    type: str  # column | column_list | choice | integer | boolean | string
    description: str
    required: bool = False
    choices: tuple[str, ...] = ()
    default: Any = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    category: str
    description: str
    params: tuple[ToolParam, ...]
    charts: tuple[str, ...]
    handler: Callable[[pd.DataFrame, Any, dict], dict]
    min_rows: int = 3
    group_param: str | None = None  # 需要分组的方法：分组参数名
    accepts: tuple[str, ...] = ()   # 目标列可接受的变量类型（空=不限）
    task: str = ""  # sta_task：描述/关联/因果/预测/决策
    applicability: str = ""  # 适用条件（显式依据，进目录与模型上下文）
    slots: tuple[str, ...] = ()  # 语义槽位：group_col/value_col/agg…

    def param(self, name: str) -> ToolParam | None:
        return next((p for p in self.params if p.name == name), None)


_CATEGORY_DESCRIBE = "描述与质检"
_CATEGORY_COMPARE = "组间比较"
_CATEGORY_MODEL = "关联与预测"

_REGISTRY: dict[str, ToolSpec] = {
    "describe": ToolSpec(
        name="describe",
        title="描述性统计",
        category=_CATEGORY_DESCRIBE,
        description="输出数值列的 n/均值/标准差/中位数/四分位，可按分组列分层描述",
        params=(
            ToolParam("group_by", "column", "分组描述所用列（可选）", required=False),
        ),
        charts=("histogram", "boxplot", "violin", "pie"),
        handler=methods.describe,
    ),
    "missing_report": ToolSpec(
        name="missing_report",
        title="缺失数据报告",
        category=_CATEGORY_DESCRIBE,
        description="逐列缺失数与缺失率（可按分组），用于缺失机制判定（MCAR/MAR/MNAR）",
        params=(
            ToolParam("group_by", "column", "按该列分组统计缺失（可选）", required=False),
        ),
        charts=(),
        handler=methods.missing_report,
    ),
    "normality_test": ToolSpec(
        name="normality_test",
        title="正态性检验",
        category=_CATEGORY_DESCRIBE,
        description="Shapiro-Wilk 正态性检验，输出 W 统计量、p 值与是否满足正态",
        params=(),
        charts=("qq_plot", "histogram"),
        handler=methods.normality_test,
        accepts=("continuous",),
    ),
    "group_compare": ToolSpec(
        name="group_compare",
        title="两组比较",
        category=_CATEGORY_COMPARE,
        description="两组连续变量比较：t 检验或 Mann-Whitney U，输出效应量 Cohen's d 与均数差 95%CI",
        params=(
            ToolParam("group_column", "column", "分组列（必填，至少 2 组）", required=True),
            ToolParam(
                "test", "choice", "检验方法；auto 按正态性自动选择",
                choices=("auto", "t", "mannwhitney"), default="auto",
            ),
            ToolParam("paired", "boolean", "是否配对样本（仅 t 检验生效）", default=False),
        ),
        charts=("boxplot", "violin"),
        handler=methods.group_compare,
        group_param="group_column",
        accepts=("continuous",),
    ),
    "anova": ToolSpec(
        name="anova",
        title="多组比较",
        category=_CATEGORY_COMPARE,
        description="多组连续变量比较：单因素 ANOVA 或 Kruskal-Wallis，输出效应量",
        params=(
            ToolParam("group_column", "column", "分组列（必填，至少 2 组）", required=True),
            ToolParam(
                "test", "choice", "检验方法；auto 按正态性自动选择",
                choices=("auto", "anova", "kruskal"), default="auto",
            ),
        ),
        charts=("boxplot", "grouped_bar", "violin"),
        handler=methods.anova,
        group_param="group_column",
        accepts=("continuous",),
    ),
    "chi_square": ToolSpec(
        name="chi_square",
        title="卡方检验",
        category=_CATEGORY_COMPARE,
        description="两个分类变量的关联检验，输出 Cramér's V；2×2 时附 OR",
        params=(
            ToolParam("row_column", "column", "行变量（target_columns 仅 1 个时必填）"),
            ToolParam("col_column", "column", "列变量（target_columns 仅 1 个时必填）"),
            ToolParam("correction", "boolean", "2×2 是否做连续性校正", default=True),
        ),
        charts=("grouped_bar", "heatmap"),
        handler=methods.chi_square,
        accepts=("categorical", "ordinal"),
    ),
    "correlation": ToolSpec(
        name="correlation",
        title="相关性分析",
        category=_CATEGORY_MODEL,
        description="Pearson/Spearman 相关矩阵与两两 p 值（至少 2 个数值列）",
        params=(
            ToolParam(
                "method", "choice", "相关系数类型",
                choices=("pearson", "spearman"), default="pearson",
            ),
        ),
        charts=("heatmap", "scatter"),
        handler=methods.correlation,
        accepts=("continuous",),
    ),
    "regression": ToolSpec(
        name="regression",
        title="线性回归",
        category=_CATEGORY_MODEL,
        description="OLS 线性回归：R²、系数 95%CI 与 p 值",
        params=(
            ToolParam("target", "column", "结局变量（数值列，必填）", required=True),
            ToolParam("features", "column_list", "自变量列表（必填，非空）", required=True),
        ),
        charts=("residual_plot", "scatter"),
        handler=methods.regression,
        accepts=("continuous",),
    ),
    "logistic_regression": ToolSpec(
        name="logistic_regression",
        title="Logistic 回归",
        category=_CATEGORY_MODEL,
        description="二分类结局的 Logistic 回归：OR 及 95%CI、准确率、AUC",
        params=(
            ToolParam("target", "column", "二分类结局（0/1，必填）", required=True),
            ToolParam("features", "column_list", "自变量列表（必填，非空）", required=True),
        ),
        charts=("bar", "grouped_bar"),
        handler=methods.logistic_regression,
    ),
    "timeseries_forecast": ToolSpec(
        name="timeseries_forecast",
        title="时间序列预测",
        category=_CATEGORY_MODEL,
        description="线性趋势拟合与外推预测（短期），输出斜率、R² 与预测值",
        params=(
            ToolParam("forecast_n", "integer", "预测期数（默认 5）", default=5),
        ),
        charts=("line",),
        handler=methods.timeseries_forecast,
        accepts=("continuous",),
    ),
}

_TASK_META = {
    "describe": ("描述", "任何分析的第一步：数值/类别列的分布概览，可按分组对比基线特征"),
    "missing_report": ("描述", "任何数据接入后必做：用于缺失机制判定（MCAR/MAR/MNAR）与数据契约确认"),
    "normality_test": ("描述", "参数/非参数方法选择的前置检验；n<3 或 n>5000 时结论需谨慎"),
    "levene_test": ("关联", "组间比较前置：判断方差齐性，决定 t/ANOVA 是否需要 Welch 校正"),
    "group_compare": ("关联", "两组独立/配对连续样本的均值差异；分组列至少 2 组且每组建议 n≥3"),
    "anova": ("关联", "三组及以上连续样本的组间差异；需分组列且各组建议 n≥3"),
    "chi_square": ("关联", "两个分类变量的独立性检验；期望频数不足时自动降级 Fisher（2×2）"),
    "correlation": ("关联", "两个及以上数值列的线性/单调关联强度；不构成因果结论"),
    "regression": ("预测", "连续结局的多因素关联与预测；自变量需数值化，样本量≥特征数×10 更稳"),
    "logistic_regression": ("预测", "二分类结局的风险因素分析（OR/AUC）；结局必须 0/1 且两类均有样本"),
    "timeseries_forecast": ("预测", "有序观测的短期趋势外推；需≥3 个有效点，仅适用无强季节性序列"),
    "aggregate_table": ("描述", "分组聚合汇总表（均值/中位数/计数等），作为交付表格或绘图数据源"),
}
_SLOT_META = {
    "describe": ("",),
    "missing_report": ("",),
    "normality_test": ("value_col",),
    "levene_test": ("group_col", "value_col"),
    "group_compare": ("group_col", "value_col"),
    "anova": ("group_col", "value_col"),
    "chi_square": ("row_col", "col_col"),
    "correlation": ("value_col",),
    "regression": ("value_col", "covariates"),
    "logistic_regression": ("outcome_col", "covariates"),
    "timeseries_forecast": ("value_col",),
    "aggregate_table": ("group_col", "value_col", "agg"),
}
for _name, (_task, _applic) in _TASK_META.items():
    _spec = _REGISTRY.get(_name)
    if _spec is not None:
        _REGISTRY[_name] = ToolSpec(
            name=_spec.name, title=_spec.title, category=_spec.category,
            description=_spec.description, params=_spec.params, charts=_spec.charts,
            handler=_spec.handler, min_rows=_spec.min_rows, group_param=_spec.group_param,
            accepts=_spec.accepts,
            task=_task, applicability=_applic,
            slots=tuple(s for s in _SLOT_META.get(_name, ()) if s),
        )

# 新增工具：方差齐性检验
_REGISTRY["levene_test"] = ToolSpec(
    name="levene_test",
    title="方差齐性检验",
    category=_CATEGORY_DESCRIBE,
    description="Levene 检验判断各组方差是否齐，决定组间比较是否需要 Welch 校正",
    params=(
        ToolParam("group_column", "column", "分组列（必填，至少 2 组）", required=True),
    ),
    charts=("boxplot",),
    handler=methods.levene_test,
    group_param="group_column",
    task="描述",
    applicability="组间比较的前置检验：连续值变量 + 分组列；与正态性检验配合决定最终检验方法",
    slots=("group_col", "value_col"),
)
_REGISTRY["aggregate_table"] = ToolSpec(
    name="aggregate_table",
    title="分组聚合表",
    category=_CATEGORY_DESCRIBE,
    description="按分组列对值变量做 mean/median/count/sum 等聚合，输出汇总表格（可交付导出）",
    params=(
        ToolParam("group_column", "column", "分组列（必填）", required=True),
        ToolParam(
            "agg", "choice", "聚合方式",
            choices=("mean", "median", "count", "sum", "std", "min", "max"), default="mean",
        ),
    ),
    charts=("grouped_bar", "pie", "bar"),
    handler=methods.aggregate_table,
    group_param="group_column",
    task="描述",
    applicability="需要汇总报表或为柱状/饼图准备聚合数据时使用；值变量应为数值列",
    slots=("group_col", "value_col", "agg"),
)

# 兼容别名：历史计划中的 hypothesis_test 等价于 group_compare
ALIASES = {"hypothesis_test": "group_compare"}

# 计划级硬错误码（阻断执行）；ORDINAL_HINT 为软提示
HARD_ISSUE_CODES = {
    "TOOL_NOT_FOUND", "COLUMN_NOT_FOUND", "MISSING_PARAM",
    "INVALID_PARAM", "INSUFFICIENT_DATA", "COLUMN_TYPE_MISMATCH",
}


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(ALIASES.get(name, name))


def all_tools() -> Iterable[ToolSpec]:
    return _REGISTRY.values()


def tool_catalog() -> list[dict]:
    """序列化目录：用于模型 info 注入与 GET /capabilities。"""
    return [
        {
            "name": spec.name,
            "title": spec.title,
            "category": spec.category,
            "description": spec.description,
            "task": spec.task,
            "applicability": spec.applicability,
            "slots": list(spec.slots),
            "params": [
                {
                    "name": param.name,
                    "type": param.type,
                    "required": param.required,
                    "description": param.description,
                    "choices": list(param.choices),
                    "default": param.default,
                }
                for param in spec.params
            ],
            "charts": list(spec.charts),
        }
        for spec in _REGISTRY.values()
    ]


def _column_names(df_or_columns: Any) -> list[str]:
    from medsta.data.profiler import TableProfile

    if isinstance(df_or_columns, pd.DataFrame):
        return list(df_or_columns.columns)
    if isinstance(df_or_columns, TableProfile):
        return list(df_or_columns.columns.keys())
    return list(df_or_columns)


def validate_step(
    step: Any, df_or_columns: pd.DataFrame | Iterable[str], index: int | None = None
) -> list[ToolIssue]:
    """校验一步计划：工具存在、列存在、必填参数、取值合法、数据充分。"""
    issues: list[ToolIssue] = []

    def add(code: ErrorCode, message: str, hint: str = "") -> None:
        issues.append(ToolIssue(code=code.value, message=message, hint=hint, step_index=index))

    spec = get_tool(step.method)
    if spec is None:
        add(
            ErrorCode.TOOL_NOT_FOUND,
            f"未知统计方法：{step.method}",
            f"可用方法：{', '.join(sorted(_REGISTRY))}",
        )
        return issues

    rationale = getattr(step, "rationale", "")
    if not str(rationale).strip():
        add(
            ErrorCode.MISSING_PARAM,
            f"步骤「{step.title}」缺少选择依据 rationale",
            "必须说明为何选择该方法：数据类型、任务性质、样本特征与方法适用性",
        )

    columns = _column_names(df_or_columns)
    column_types = _resolve_types(df_or_columns)
    for column in step.target_columns:
        col_type = column_types.get(column)
        if col_type == "index":
            add(
                ErrorCode.COLUMN_TYPE_MISMATCH,
                f"列「{column}」为序列索引类型，默认不参与统计",
                "如确需分析请在画像中把类型改为连续型",
            )
        elif col_type == "ordinal" and spec.accepts and "continuous" in spec.accepts and "ordinal" not in spec.accepts:
            issues.append(ToolIssue(
                code="ORDINAL_HINT",
                message=f"列「{column}」是数值-等级型：参数检验前提不稳，将自动按非参数/稳健方法处理",
                hint="次优方案：Mann-Whitney / Kruskal-Wallis；或改用卡方与频数描述",
                step_index=index,
            ))
        elif (
            spec.accepts
            and col_type in ("categorical", "ordinal", "continuous")
            and col_type not in spec.accepts
        ):
            suggestion = {
                "categorical": "类别型可用 chi_square 或频数描述",
                "ordinal": "等级型建议非参数方法（Mann-Whitney / Kruskal-Wallis）",
                "continuous": "连续型建议分箱后用卡方，或改用连续型方法",
            }.get(col_type, "")
            add(
                ErrorCode.COLUMN_TYPE_MISMATCH,
                f"列「{column}」是{col_type}型，不适用于 {spec.name}",
                suggestion,
            )
    for column in step.target_columns:
        if column not in columns:
            add(
                ErrorCode.COLUMN_NOT_FOUND,
                f"步骤「{step.title}」引用了不存在的列：{column}",
                f"数据现有列：{', '.join(columns[:12])}",
            )
    if not step.target_columns:
        add(ErrorCode.INVALID_PARAM, f"步骤「{step.title}」至少需要一个目标列")

    if step.chart_type != "none" and step.chart_type not in spec.charts:
        add(
            ErrorCode.INVALID_PARAM,
            f"方法 {spec.name} 不支持图表 {step.chart_type}",
            f"可用图表：{', '.join(spec.charts) or 'none'}",
        )

    params = dict(step.params or {})
    for param in spec.params:
        value = params.get(param.name)
        if (value is None or value == "" or value == []) and param.required:
            add(
                ErrorCode.MISSING_PARAM,
                f"步骤「{step.title}」缺少必填参数 {param.name}",
                f"{param.name}：{param.description}",
            )
            continue
        if value is None or value == "":
            continue
        if param.type == "column" and value not in columns:
            add(
                ErrorCode.COLUMN_NOT_FOUND,
                f"参数 {param.name} 引用了不存在的列：{value}",
                f"数据现有列：{', '.join(columns[:12])}",
            )
        elif param.type == "column_list":
            if not isinstance(value, list) or not value:
                add(ErrorCode.INVALID_PARAM, f"参数 {param.name} 需为非空列名数组")
            else:
                unknown = [c for c in value if c not in columns]
                if unknown:
                    add(
                        ErrorCode.COLUMN_NOT_FOUND,
                        f"参数 {param.name} 含不存在的列：{', '.join(map(str, unknown))}",
                        f"数据现有列：{', '.join(columns[:12])}",
                    )
        elif param.type == "choice" and param.choices and value not in param.choices:
            add(
                ErrorCode.INVALID_PARAM,
                f"参数 {param.name} 取值非法：{value}",
                f"可选值：{', '.join(param.choices)}",
            )
        elif param.type == "integer":
            try:
                int(value)
            except (TypeError, ValueError):
                add(ErrorCode.INVALID_PARAM, f"参数 {param.name} 需为整数，收到 {value!r}")

    hard_issues = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]
    if hard_issues:
        return hard_issues  # 软提示（ORDINAL_HINT 等）继续走数据充分性检查

    # chi_square 的两列来源：target_columns 或 params
    if spec.name == "chi_square" and len(step.target_columns) < 2:
        for name in ("row_column", "col_column"):
            if params.get(name) is None:
                add(
                    ErrorCode.MISSING_PARAM,
                    f"步骤「{step.title}」缺少必填参数 {name}",
                    "chi_square 需两个分类列：可用 target_columns 给 2 列，或填 row_column/col_column",
                )

    hard_issues = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]
    if hard_issues:
        return hard_issues

    if isinstance(df_or_columns, pd.DataFrame):
        issues.extend(_check_data(spec, step, df_or_columns, params, index))
    return issues


def _check_data(
    spec: ToolSpec, step: Any, df: pd.DataFrame, params: dict, index: int | None
) -> list[ToolIssue]:
    issues: list[ToolIssue] = []

    def add(code: ErrorCode, message: str, hint: str = "") -> None:
        issues.append(ToolIssue(code=code.value, message=message, hint=hint, step_index=index))

    if spec.name in ("missing_report", "describe", "aggregate_table"):
        # 这三个方法原生支持分类列，不做数值量检查
        return issues

    if spec.group_param:
        group_column = params.get(spec.group_param)
        if group_column:
            group_count = df[group_column].nunique(dropna=True)
            if group_count < 2:
                add(
                    ErrorCode.INSUFFICIENT_DATA,
                    f"分组列「{group_column}」只有 {group_count} 组，至少需要 2 组",
                    "换一个分组列，或先上传含多组的数据",
                )
            elif spec.name == "group_compare" and group_count > 2:
                # group_compare 只比较前两组；静默丢弃第三组会造成错误结论
                add(
                    ErrorCode.INVALID_PARAM,
                    f"分组列「{group_column}」有 {group_count} 组，两组比较只覆盖前两组",
                    "多组比较请改用 anova；或先筛选/合并为两组再比较",
                )
            for column in step.target_columns:
                valid = pd.to_numeric(df[column], errors="coerce").dropna()
                if len(valid) < spec.min_rows:
                    add(
                        ErrorCode.INSUFFICIENT_DATA,
                        f"列「{column}」有效数值仅 {len(valid)} 个，至少需要 {spec.min_rows} 个",
                    )
            return issues

    if spec.name == "chi_square":
        if len(step.target_columns) >= 2:
            first, second = step.target_columns[0], step.target_columns[1]
        else:
            first, second = params["row_column"], params["col_column"]
        if df[first].nunique() < 2 or df[second].nunique() < 2:
            add(ErrorCode.INSUFFICIENT_DATA, "列联表需每个变量至少 2 个类别")
        return issues

    for column in step.target_columns:
        valid = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(valid) < spec.min_rows:
            add(
                ErrorCode.INSUFFICIENT_DATA,
                f"列「{column}」有效数值仅 {len(valid)} 个，至少需要 {spec.min_rows} 个",
            )
    if spec.name == "logistic_regression":
        target = params.get("target")
        if target and target in df.columns:
            values = set(pd.to_numeric(df[target], errors="coerce").dropna().unique())
            if not values <= {0.0, 1.0}:
                add(
                    ErrorCode.INVALID_PARAM,
                    f"logistic 回归结局「{target}」必须为 0/1 二分类",
                    "请先对结局做二值化，或改用线性回归",
                )
    return issues


def validate_plan(plan: Any, df_or_columns: pd.DataFrame | Iterable[str]) -> list[ToolIssue]:
    issues: list[ToolIssue] = []
    for index, step in enumerate(plan.steps):
        issues.extend(validate_step(step, df_or_columns, index))
    return issues


def normalize_params(spec: ToolSpec, step: Any) -> dict:
    params = dict(step.params or {})
    for param in spec.params:
        if params.get(param.name) in (None, "", []) and param.default is not None:
            params[param.name] = param.default
    return params


def execute_step(
    df: pd.DataFrame, step: Any, artifact_dir: Any, index: int
) -> tuple[dict, str | None]:
    """执行一步并渲染图表；调用方应先用 validate_step 校验。"""
    import pathlib

    spec = get_tool(step.method)
    if spec is None:
        raise ValueError(f"未知统计方法：{step.method}")
    params = normalize_params(spec, step)
    result = spec.handler(df, step, params)
    artifact: str | None = None
    if step.chart_type != "none":
        path = render_chart(df, step, pathlib.Path(artifact_dir), index, result=result)
        result["artifact"] = path.name
        artifact = path.name
    return result, artifact


def _resolve_types(df_or_profile: Any) -> dict[str, str]:
    """解析列类型：DataFrame 现场推断；TableProfile 直接取用户敲定值。"""
    from medsta.data.profiler import TableProfile, _infer_column_type

    if isinstance(df_or_profile, TableProfile):
        return {name: col.type for name, col in df_or_profile.columns.items()}
    if isinstance(df_or_profile, pd.DataFrame):
        types: dict[str, str] = {}
        for position, (name, series) in enumerate(df_or_profile.items()):
            inferred = _infer_column_type(series, str(name), position)
            # 未敲定画像时，index 只是推断建议，不据此拒绝统计
            types[str(name)] = "continuous" if inferred == "index" else inferred
        return types
    return {}

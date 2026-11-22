"""内置推荐工作链模板（recipe）：把方法学 skills 落成「可载入的流程」。

与「用户模板」（`session/templates.py` 存在 data/templates）不同，recipe 是系统内置、
只读、按数据画像做参数匹配的骨架：
- 模板里的列位置用**语义占位**（group / continuous_primary / time / event …）描述；
- 载入时由宿主筛候选列（确定性：类型 + 组数 + 取值），再由模型在候选中做语义选择；
- 模型不可用时退回规则匹配（取首个候选），并标注 `matched_by`。

这样「默认推荐工具链」与「实际数据参数」之间有一层经过校验的桥，用户仍可在装配区改。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from medsta.stats.registry import tool_catalog

# ---- 占位语义 ----

SLOT_LABELS: dict[str, str] = {
    "group": "分组列（2~10 组）",
    "continuous_primary": "主要连续指标",
    "categorical_feature": "分类特征",
    "binary_outcome": "二分类结局（0/1）",
    "time": "随访时间",
    "event": "事件指示（0/1）",
    "feature_list": "候选影响因素（2~4 列）",
    "numeric_features": "数值协变量（1~4 列）",
}


def _distinct(df: pd.DataFrame, column: str) -> int:
    try:
        return int(df[column].nunique(dropna=True))
    except Exception:
        return 0


def _positive(df: pd.DataFrame, column: str) -> bool:
    try:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        return bool(len(series)) and bool((series >= 0).all()) and float(series.max()) > 0
    except Exception:
        return False


def candidates_for(
    df: pd.DataFrame, profile: Any, slot: str, exclude: set[str] | None = None
) -> list[str]:
    """按占位语义筛候选列（宿主确定性规则，模型只在候选中挑）。"""
    exclude = exclude or set()
    types = {name: col.type for name, col in profile.columns.items()}
    ordered = [name for name in types if name not in exclude]

    def typed(*kinds: str) -> list[str]:
        return [name for name in ordered if types.get(name) in kinds]

    continuous = typed("continuous", "ordinal")
    categorical = typed("categorical")

    if slot == "group":
        return [col for col in categorical if 2 <= _distinct(df, col) <= 10]
    if slot == "continuous_primary":
        return typed("continuous")
    if slot == "categorical_feature":
        return [col for col in categorical if _distinct(df, col) >= 2]
    if slot == "binary_outcome":
        return [
            col
            for col in categorical + typed("ordinal")
            if _distinct(df, col) == 2
        ]
    if slot == "time":
        return [col for col in continuous if _positive(df, col)]
    if slot == "event":
        return [col for col in categorical + typed("ordinal") if _distinct(df, col) == 2]
    if slot == "feature_list":
        return (categorical + continuous)[:6]
    if slot == "numeric_features":
        return continuous[:6]
    return []


# ---- 模板定义 ----


@dataclass(frozen=True)
class RecipeStep:
    title: str
    method: str
    chart_type: str = "none"
    rationale: str = ""
    # 目标列占位（如 ("continuous_primary",)）
    targets: tuple[str, ...] = ()
    # 参数占位（参数名 → 占位语义）
    params: dict[str, str] = field(default_factory=dict)
    # 固定参数（不参与匹配）
    fixed: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    description: str
    skill: str
    steps: tuple[RecipeStep, ...]

    def slots(self) -> list[str]:
        found: list[str] = []
        for step in self.steps:
            for slot in list(step.targets) + list(step.params.values()):
                if slot not in found:
                    found.append(slot)
        return found


RECIPES: tuple[Recipe, ...] = (
    Recipe(
        id="quality_baseline",
        title="数据质量与基线描述",
        description="先量化缺失与异常，再给出主要指标与分组构成——写论文「基线表」的标准起点。",
        skill="missing_data",
        steps=(
            RecipeStep(
                title="缺失与数据质量报告",
                method="missing_report",
                rationale="分析前先确认缺失量与模式，避免后续检验建立在不可靠样本上。",
            ),
            RecipeStep(
                title="主要指标分布描述",
                method="describe",
                targets=("continuous_primary",),
                chart_type="histogram",
                rationale="连续变量先看分布形态，据此决定用均值±SD 还是中位数(P25~P75)描述。",
            ),
            RecipeStep(
                title="分组构成（率与频数）",
                method="chi_square",
                chart_type="grouped_bar",
                params={"row_column": "group", "col_column": "categorical_feature"},
                rationale="分组构成用卡方比较率差，并给各组 n 与百分比。",
            ),
        ),
    ),
    Recipe(
        id="two_group_compare",
        title="两组基线比较",
        description="两组（如手术/非手术）主要指标的组间比较：描述 + 正态性判断 + 非参数/参数并行。",
        skill="continuous_two_group",
        steps=(
            RecipeStep(
                title="两组主要指标描述",
                method="describe",
                targets=("continuous_primary",),
                rationale="先给两组各自的 n 与离散度，比较才有解释基础。",
            ),
            RecipeStep(
                title="组间比较（按正态性与方差齐性择优）",
                method="group_compare",
                targets=("continuous_primary",),
                chart_type="boxplot",
                params={"group_column": "group"},
                rationale="两组连续变量比较：正态且方差齐用 t，方差不齐用 Welch，非正态用 Mann-Whitney。",
            ),
        ),
    ),
    Recipe(
        id="multi_group_compare",
        title="多组比较（ANOVA + 事后）",
        description="≥3 组的连续指标比较：总体检验 + 事后两两比较（Holm 校正），避免多次 t 检验膨胀假阳性。",
        skill="continuous_multi_group",
        steps=(
            RecipeStep(
                title="各组主要指标描述",
                method="describe",
                targets=("continuous_primary",),
                rationale="先看各组 n 与分布，样本过小的组需在结论里说明把握度不足。",
            ),
            RecipeStep(
                title="多组比较（ANOVA/Kruskal + 事后）",
                method="anova",
                targets=("continuous_primary",),
                chart_type="boxplot",
                params={"group_column": "group"},
                fixed={"correction": "holm"},
                rationale="三组及以上用方差分析；非正态改 Kruskal-Wallis，事后比较统一 Holm 校正。",
            ),
        ),
    ),
    Recipe(
        id="logistic_risk",
        title="影响因素 Logistic 回归",
        description="二分类结局的影响因素探索：先描述，再多因素模型（事件数不足时只做单因素）。",
        skill="correlation_regression",
        steps=(
            RecipeStep(
                title="结局与候选因素分布",
                method="describe",
                targets=("continuous_primary",),
                rationale="建模前先确认结局比例与候选因素的分布/缺失，避免分离与共线性。",
            ),
            RecipeStep(
                title="多因素 Logistic 回归",
                method="logistic_regression",
                chart_type="bar",
                params={"target": "binary_outcome", "features": "feature_list"},
                rationale="报告 OR 与 95%CI；事件数（EPV）不足时只做单因素并标注为探索性。",
            ),
        ),
    ),
    Recipe(
        id="survival_basic",
        title="生存分析（KM + log-rank）",
        description="带随访时间的结局分析：KM 曲线与中位生存期，组间 log-rank，必要时 Cox 多因素。",
        skill="survival",
        steps=(
            RecipeStep(
                title="KM 估计与中位生存期",
                method="survival_analysis",
                chart_type="survival_curve",
                params={"time_col": "time", "event_col": "event", "group_col": "group"},
                fixed={"method": "km", "test": "logrank"},
                rationale="先给 KM 曲线、中位生存期与删失比例；组间差异用 log-rank。",
            ),
            RecipeStep(
                title="Cox 多因素（HR + PH 检验）",
                method="survival_analysis",
                params={
                    "time_col": "time",
                    "event_col": "event",
                    "covariates": "numeric_features",
                },
                fixed={"method": "cox"},
                rationale="多因素用 Cox 报告 HR+CI，并检查 PH 假设（Schoenfeld）。",
            ),
        ),
    ),
)

_BY_ID = {recipe.id: recipe for recipe in RECIPES}


def recipe_catalog() -> list[dict]:
    """模板目录（前端渲染推荐卡；含占位语义标签）。"""
    tools = {tool["name"] for tool in tool_catalog()}
    catalog: list[dict] = []
    for recipe in RECIPES:
        catalog.append(
            {
                "id": recipe.id,
                "title": recipe.title,
                "description": recipe.description,
                "skill": recipe.skill,
                "steps": [
                    {
                        "title": step.title,
                        "method": step.method,
                        "chart_type": step.chart_type,
                        "targets": list(step.targets),
                        "params": dict(step.params),
                        "fixed": dict(step.fixed),
                        "rationale": step.rationale,
                        "method_available": step.method in tools,
                    }
                    for step in recipe.steps
                ],
                "slots": [
                    {"slot": slot, "label": SLOT_LABELS.get(slot, slot)} for slot in recipe.slots()
                ],
            }
        )
    return catalog


def get_recipe(recipe_id: str) -> Recipe | None:
    return _BY_ID.get(recipe_id)


@dataclass
class MatchResult:
    steps: list[dict]
    matched: list[dict]
    warnings: list[str]


def match_recipe(
    recipe: Recipe,
    df: pd.DataFrame,
    profile: Any,
    choices: dict[str, str] | None = None,
) -> MatchResult:
    """按占位语义填充模板参数。

    `choices`（模型给出的 slot→column）只在其属于**宿主候选集合**时才被采纳，
    其余回退首个候选——模型做语义选择，宿主负责合法性与可执行性。
    """
    choices = choices or {}
    used: set[str] = set()
    steps: list[dict] = []
    matched: list[dict] = []
    warnings: list[str] = []

    for index, step in enumerate(recipe.steps):
        assignments: dict[str, Any] = {}
        by_slot: dict[str, str] = {}
        blocked = False

        slots: list[tuple[str, bool]] = [(slot, False) for slot in step.targets]
        slots += [(slot, True) for slot in step.params.values()]

        for slot, is_param in slots:
            pool = candidates_for(
                df, profile, slot, exclude=used | set(v for v in assignments.values() if isinstance(v, str))
            )
            if not pool:
                label = SLOT_LABELS.get(slot, slot)
                warnings.append(
                    f"第 {index + 1} 步「{step.title}」缺少可用列（{label}），已跳过该步"
                )
                blocked = True
                break
            picked = choices.get(slot)
            list_slot = slot in ("feature_list", "numeric_features")
            if picked in pool:
                value: Any = [picked] if list_slot else picked
                by_slot[slot] = "ai"
            else:
                value = pool[: min(4, len(pool))] if list_slot else pool[0]
                by_slot[slot] = "rule"
            assignments[slot] = value
            if isinstance(value, str):
                used.add(value)

        if blocked:
            continue

        targets = [assignments[slot] for slot in step.targets]
        params: dict[str, Any] = dict(step.fixed)
        for param, slot in step.params.items():
            params[param] = assignments[slot]

        steps.append(
            {
                "title": step.title,
                "method": step.method,
                "target_columns": targets,
                "chart_type": step.chart_type,
                "params": params,
                "rationale": step.rationale,
            }
        )
        matched.extend(
            {"step": len(steps) - 1, "slot": slot, "column": assignments[slot], "by": by_slot[slot]}
            for slot in assignments
        )

    return MatchResult(steps=steps, matched=matched, warnings=warnings)


def rule_match(recipe: Recipe, df: pd.DataFrame, profile: Any) -> MatchResult:
    """纯规则匹配（无模型/模型失败时的确定性兜底）。"""
    return match_recipe(recipe, df, profile, choices=None)

"""能力披露：前端展示助手可做的统计方法与图表（含规划中能力）。"""
from __future__ import annotations

from fastapi import APIRouter

from medsta.stats.plotting import CHART_LABELS
from medsta.stats.registry import CHART_TYPES, tool_catalog

router = APIRouter()

# 方法学上重要但本期未实现的能力：显式披露，避免前端过度承诺
_PLANNED = [
    {
        "name": "survival_analysis",
        "title": "生存分析",
        "description": "Cox 比例风险、Kaplan-Meier、RMST、Fine-Gray 竞争风险（需引入 lifelines）",
        "status": "planned",
    },
    {
        "name": "multiple_imputation",
        "title": "多重插补",
        "description": "MICE 多重插补与 tipping point 敏感性分析（对应缺失决策板 C）",
        "status": "planned",
    },
    {
        "name": "multiplicity_control",
        "title": "多重性校正",
        "description": "Holm / Hochberg / Dunnett 与层级 gatekeeping（对应决策板 D）",
        "status": "planned",
    },
]


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "tools": tool_catalog(),
        "charts": [
            {"name": name, "label": CHART_LABELS.get(name, name)}
            for name in CHART_TYPES
            if name != "none"
        ],
        "planned": _PLANNED,
        "methodology": "依据《医学统计处理流程图》《顶刊统计策略图谱》决策表落地",
    }

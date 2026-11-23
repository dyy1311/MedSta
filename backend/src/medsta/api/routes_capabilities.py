"""能力披露：前端展示助手可做的统计方法与图表（含规划中能力）。"""
from __future__ import annotations

from fastapi import APIRouter

from medsta.stats.plotting import CHART_LABELS
from medsta.stats.registry import CHART_TYPES, tool_catalog

router = APIRouter()

# 方法学上重要但本期未实现的能力：显式披露，避免前端过度承诺
_PLANNED = [
    {
        "name": "competing_risk",
        "title": "竞争风险（Fine-Gray）",
        "description": (
            "子分布风险模型（Fine-Gray）与累积发生函数未实现；"
            "当前生存分析只支持右删失的单一终点，竞争事件不能当作独立删失处理"
        ),
        "status": "planned",
    },
    {
        "name": "multiple_imputation",
        "title": "完整多重插补（Rubin 合并）",
        "description": (
            "当前 impute 为单数据集插补（标准误偏小）；"
            "m 次插补后按 Rubin 规则合并的完整 MI 与 tipping point 未实现"
        ),
        "status": "planned",
    },
    {
        "name": "sap_export",
        "title": "SAP 摘要导出与事前注册",
        "description": (
            "当前仅在方案卡展示估计目标（ICH E9(R1) 五要素）；"
            "SAP 文档导出、版本号与事前注册信息未实现"
        ),
        "status": "planned",
    },
    {
        "name": "multiplicity_control",
        "title": "多重性校正",
        "description": (
            "已实现：Holm、Dunnett、Tukey、Schéffé、SNK-q、LSD-t 与 Bonferroni；"
            "未实现：Hochberg、层级 gatekeeping、图形法与期中 α 消耗"
        ),
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

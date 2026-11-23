"""模型辅助列类型确认（041）。

Owner 合规：模型只做语义决策（列的测量学含义 → 类型建议 + 理由），
宿主组装证据白名单并校验建议类型，用户保留最终敲定权。
"""
from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field

from medsta.config import ModelGateway


class ColumnTypeSuggestion(BaseModel):
    name: str = Field(default="", description="原列名（不得改写）")
    suggested_type: str = Field(default="", description="continuous/ordinal/categorical/index 之一")
    confidence: float = Field(default=0.8, description="0-1 置信度")
    reason: str = Field(default="", description="一句话判断依据")


class ColumnAdviceReport(BaseModel):
    columns: list[ColumnTypeSuggestion] = Field(default_factory=list)


_OUTPUT_FIELDS = {
    "columns": (
        list,
        "列类型建议数组，每项含 name(原列名，不得改写)/suggested_type"
        "(continuous/ordinal/categorical/index 之一)/confidence(0-1)/reason(一句话依据)",
    )
}


class ColumnTypeAdvisor:
    """基于证据（列名语义+样本值+统计特征）给出列类型建议。"""

    def __init__(self, gateway: ModelGateway) -> None:
        self._gateway = gateway

    def advise(self, evidence: list[dict]) -> ColumnAdviceReport:
        import json

        instruction = (
            "你是医学统计的数据管理员。逐列判断其测量学类型：\n"
            "- continuous：连续测量指标（均值/标准差有意义）\n"
            "- ordinal：数值-等级（分期、评分、 Likertz 等有限有序取值）\n"
            "- categorical：类别（分组、性别、无序编码）\n"
            "- index：序列标识符（编号、日期时间索引，统计默认排除）\n"
            "结合列名语义、样本取值与统计特征判断；对每列给出建议类型与理由。"
        )
        return cast(
            ColumnAdviceReport,
            self._gateway.request_structured(
                ColumnAdviceReport,
                fields=_OUTPUT_FIELDS,
                input=json.dumps(evidence, ensure_ascii=False, default=str),
                instruct=instruction,
            ),
        )

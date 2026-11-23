"""工作链模板的「AI 一键匹配」：模型在宿主候选集内为占位槽位挑列。

边界：候选列由宿主按类型/组数/取值确定性筛出（`chain_recipes.candidates_for`），
模型只负责语义层面「哪个候选更像分组列/随访时间/结局」，最终由 `match_recipe` 复核
候选合法性——模型给出候选外的列时会被丢弃并回退规则匹配。
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from medsta.agents.chain_recipes import SLOT_LABELS, Recipe


class SlotChoice(BaseModel):
    slot: str = Field(description="占位槽位名，如 group / time / binary_outcome")
    column: str = Field(description="选中的真实列名（必须来自候选）")


class ChainAssignments(BaseModel):
    assignments: list[SlotChoice] = Field(default_factory=list)


_FIELDS: dict[str, tuple] = {
    "assignments": (list[dict], "占位槽位到真实列的映射：slot(str)/column(str)；无合适列时省略该槽位"),
}


class ChainMatchAgent:
    """一次结构化匹配请求（不做多轮，不做重试——失败即回退规则匹配）。"""

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    def match(
        self,
        *,
        recipe: Recipe,
        candidates: dict[str, list[str]],
        profile_json: str,
    ) -> dict[str, str]:
        slots = [
            {
                "slot": slot,
                "label": SLOT_LABELS.get(slot, slot),
                "candidates": candidates.get(slot, []),
            }
            for slot in recipe.slots()
        ]
        info = (
            f"数据画像（JSON）：{profile_json}\n"
            f"工作流模板：{recipe.title}——{recipe.description}\n"
            f"占位槽位与候选列（只能从 candidates 里选）：{json.dumps(slots, ensure_ascii=False)}"
        )
        instruct = (
            "为每个占位槽位从它自己的 candidates 中挑选最合适的一列："
            "group 是用于分组比较的类别列（2~10 组）；time 是随访时间；event 是 0/1 事件指示；"
            "binary_outcome 是二分类结局；continuous_primary 是主要连续指标；feature_list 是影响因素（选 2~4 个）。"
            "candidates 为空或没有合适列时，省略该槽位，不要发明列名。"
        )
        result = self._gateway.request_structured(
            ChainAssignments,
            fields=_FIELDS,
            input="为工作流模板匹配真实数据列",
            info=info,
            instruct=instruct,
        )
        assignments = getattr(result, "assignments", []) or []
        return {
            choice.slot: choice.column
            for choice in assignments
            if choice.slot and choice.column
        }

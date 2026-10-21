"""ReAct 讨论智能体与 AnalysisPlan 结构化契约。

Owner 划分：模型做语义决策（选方法/定步骤/写说明）；宿主做契约校验
（枚举约束、目标列必须存在于画像）。单次交互由 ModelRequest 四段式承载。
"""
from __future__ import annotations

import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from medsta.config import ModelGateway
from medsta.data.profiler import TableProfile
from medsta.errors import ToolValidationError
from medsta.stats.registry import HARD_ISSUE_CODES, tool_catalog, validate_plan

MethodType = Literal[
    "describe",
    "missing_report",
    "normality_test",
    "levene_test",
    "group_compare",
    "anova",
    "chi_square",
    "correlation",
    "regression",
    "logistic_regression",
    "timeseries_forecast",
    "aggregate_table",
    "hypothesis_test",  # 兼容别名：等价 group_compare
]
ChartType = Literal[
    "histogram", "boxplot", "violin", "scatter", "line",
    "bar", "grouped_bar", "heatmap", "qq_plot", "residual_plot", "pie", "none",
]


class PlanStep(BaseModel):
    step_id: str | None = Field(default=None, description="步骤唯一 id（前端配置引用）")
    title: str = Field(description="步骤标题")
    method: MethodType = Field(description="分析方法（工具目录中的 name）")
    target_columns: list[str] = Field(description="目标列名，必须来自数据画像")
    chart_type: ChartType = Field(description="图表类型（枚举），无需图表时用 none")
    params: dict = Field(default_factory=dict, description="步骤参数（必填项见工具目录）")
    rationale: str = Field(
        default="",
        description="选择依据：为何选此方法/参数（数据类型、任务性质、样本特征、方法适用性）",
    )


class PlanOption(BaseModel):
    """方案交互选项：前端按钮，选中后回到宿主状态机执行。"""

    id: str = Field(description="选项唯一 id")
    label: str = Field(description="按钮文案（简体中文，≤12 字）")
    action: Literal["confirm", "revise", "explain", "custom", "supplement"] = Field(
        description="动作：confirm 执行 / revise 换方法 / explain 解释依据 / custom 自定义 / supplement 补充对话"
    )
    description: str = Field(default="", description="选项说明（可选）")


class AnalysisPlan(BaseModel):
    message: str = Field(description="给用户的方案说明")
    steps: list[PlanStep] = Field(description="按执行顺序排列的分析步骤")
    options: list[PlanOption] = Field(
        default_factory=list, description="给用户的可选项（必须含 confirm）"
    )

    def method_summary(self) -> str:
        return " -> ".join(f"{s.title}({s.method})" for s in self.steps)


_BASE_INSTRUCT = (
    "你是面向数据研究者的数据分析方案设计师。按以下链条拆解统计任务，每一步都显式说明依据：\n"
    "1) 定性统计任务 sta_task：描述 / 关联 / 因果 / 预测 / 决策（先想清楚『问什么』）；\n"
    "2) 明确变量槽位：分组变量（group_column/group_by）与值变量（target_columns），必须来自数据画像列名；\n"
    "3) 从『可用统计工具目录』选择 method（注意每个方法的 applicability 适用条件），"
    "params 必填槽位必须按目录给全（缺参会被宿主拒绝）；\n"
    "4) 检验策略由执行期自动完成（正态性 → 方差齐性 → 最优/次优方法），"
    "若数据可能不满足前提请在 message 中预告并说明降级路径；\n"
    "5) 每个步骤必须填写 rationale：为何选此方法与参数（数据类型、任务性质、样本特征、方法适用性），缺失会被拒绝；\n"
    "6) 显著性规范：默认 α=0.05，多组两两比较将按 Holm 校正；如数据特征建议其他 α 或校正方式，在 message 中说明；\n"
    "7) options 给出 2–4 个行动选项，必须包含一个 action=confirm 的执行选项，"
    "可按需给出 revise（换方法）/explain（解释依据）/supplement（补充对话）；\n"
    "message 用简体中文说明方案思路、预期产出与显著性判断建议。"
)

_OUTPUT_FIELDS = {
    "message": (str, "给用户的方案说明"),
    "steps": (
        list,
        "步骤数组，每项含 title(str)/method(工具目录中的 name)/"
        "target_columns(list[str])/chart_type(该工具 charts 之一或 none)/params(object，必填项见工具目录)",
    ),
    "options": (
        list,
        "行动选项数组，每项含 id(str, 唯一)/label(str)/action(confirm|revise|explain|custom|supplement)/description(str)",
    ),
}




class DiscussionAgent:
    """讨论态智能体：画像 + 诉求 -> AnalysisPlan + 讨论消息。

    request_factory 仅用于测试在模型传输边界注入模拟实现。
    """

    def __init__(
        self,
        gateway: ModelGateway | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        # gateway 与 request_factory 二选一：测试注入 request_factory，生产经 gateway
        self._gateway = gateway
        self._request_factory = request_factory

    def draft_plan(
        self,
        profile: TableProfile,
        user_request: str,
        revision_note: str | None = None,
    ) -> AnalysisPlan:
        instruct = _BASE_INSTRUCT
        if revision_note:
            instruct += f"\n用户修正意见（必须遵守）：{revision_note}"
        catalog = json.dumps(tool_catalog(), ensure_ascii=False)
        types_summary = json.dumps(
            {name: col.type for name, col in profile.columns.items()}, ensure_ascii=False
        )
        info = (
            f"数据画像：{profile.model_dump_json()}\n"
            f"列变量类型（continuous 连续/ordinal 等级/categorical 类别/index 索引）：{types_summary}\n"
            f"可用统计工具目录（JSON）：{catalog}"
        )
        request = self._build_request()
        plan = request(input=user_request, info=info, instruct=instruct)
        self._validate_plan(plan, profile)
        _assign_step_ids(plan)
        plan.options = _normalize_options(plan.options)
        return plan

    async def draft_plan_stream(
        self,
        *,
        profile: TableProfile,
        user_request: str,
        revision_note: str | None = None,
        on_delta: Callable[[str], Any] | None = None,
    ) -> AnalysisPlan:
        """流式草拟方案：增量文本经 on_delta 推送，最终返回校验后的计划。"""
        gateway = self._gateway
        if gateway is None or not hasattr(gateway, "request_structured_stream"):
            return self.draft_plan(
                profile=profile, user_request=user_request, revision_note=revision_note
            )
        instruct = _BASE_INSTRUCT
        if revision_note:
            instruct += f"\n用户修正意见（必须遵守）：{revision_note}"
        catalog = json.dumps(tool_catalog(), ensure_ascii=False)
        types_summary = json.dumps(
            {name: col.type for name, col in profile.columns.items()}, ensure_ascii=False
        )
        info = (
            f"数据画像：{profile.model_dump_json()}\n"
            f"列变量类型（continuous 连续/ordinal 等级/categorical 类别/index 索引）：{types_summary}\n"
            f"可用统计工具目录（JSON）：{catalog}"
        )
        plan = await gateway.request_structured_stream(
            AnalysisPlan,
            fields=_OUTPUT_FIELDS,
            input=user_request,
            info=info,
            instruct=instruct,
            on_delta=on_delta,
        )
        self._validate_plan(plan, profile)
        _assign_step_ids(plan)
        plan.options = _normalize_options(plan.options)
        return plan

    def _build_request(self) -> Callable[..., AnalysisPlan]:
        if self._request_factory is not None:
            fake = self._request_factory()
            return lambda *, input, info, instruct: self._run(fake, input, info, instruct)
        assert self._gateway is not None, "需要 gateway 或 request_factory 之一"
        return lambda *, input, info, instruct: self._run_gateway(
            self._gateway, input, info, instruct
        )

    @staticmethod
    def _run(fake: Any, input: str, info: str, instruct: str) -> AnalysisPlan:
        fields = _OUTPUT_FIELDS
        raw = (
            fake.input(input)
            .info(info)
            .instruct(instruct)
            .output(fields, format="json")
            .start()
        )
        return AnalysisPlan.model_validate(raw)

    @staticmethod
    def _run_gateway(
        gateway: ModelGateway, input: str, info: str, instruct: str
    ) -> AnalysisPlan:
        fields = _OUTPUT_FIELDS
        return gateway.request_structured(
            AnalysisPlan, fields=fields, input=input, info=info, instruct=instruct
        )

    @staticmethod
    def _validate_plan(plan: AnalysisPlan, profile: TableProfile) -> None:
        """宿主确定性校验：硬错误（工具/列/参数/类型不匹配）才拒绝；软提示放行。"""
        issues = validate_plan(plan, profile)
        hard = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]
        if hard:
            raise ToolValidationError(hard)


def _assign_step_ids(plan: AnalysisPlan) -> None:
    """宿主保证每步有唯一 step_id（前端图表配置引用）。"""
    for index, step in enumerate(plan.steps):
        if not step.step_id:
            step.step_id = f"step_{index + 1}"


_DEFAULT_CONFIRM = PlanOption(
    id="confirm",
    label="按此执行",
    action="confirm",
    description="确认当前方案并开始执行",
)


def _normalize_options(options: list[PlanOption]) -> list[PlanOption]:
    """宿主保证：id 唯一、必须含 confirm、最多 4 个。"""
    seen: set[str] = set()
    unique: list[PlanOption] = []
    for option in options:
        if option.id in seen:
            continue
        seen.add(option.id)
        unique.append(option)
    if not any(option.action == "confirm" for option in unique):
        unique.insert(0, _DEFAULT_CONFIRM)
    return unique[:4]

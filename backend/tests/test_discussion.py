"""003 讨论智能体：draft_plan 公共接口测试（模拟模型，传输边界注入）。"""
import pandas as pd
import pytest
from pydantic import ValidationError

from medsta.agents.discussion import AnalysisPlan, DiscussionAgent
from medsta.data.profiler import profile_dataframe


class FakeRequest:
    """模拟模型传输边界：记录四段式契约，返回预置 payload。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.input_value = None
        self.info_value = None
        self.instruct_value = None
        self.fields = None

    def input(self, value) -> "FakeRequest":
        self.input_value = value
        return self

    def info(self, value) -> "FakeRequest":
        self.info_value = value
        return self

    def instruct(self, value) -> "FakeRequest":
        self.instruct_value = value
        return self

    def output(self, fields, **kwargs) -> "FakeRequest":
        self.fields = fields
        return self

    def start(self) -> dict:
        return self._payload


def _profile() -> "object":
    df = pd.DataFrame(
        {
            "month": ["1月", "2月", "3月", "4月"],
            "sales": [120.0, 135.5, 128.0, 150.0],
            "region": ["east", "west", "east", "east"],
        }
    )
    return profile_dataframe(df)


def _agent(payload: dict) -> tuple:
    fake = FakeRequest(payload)
    agent = DiscussionAgent(gateway=object(), request_factory=lambda: fake)
    return agent, fake


def test_draft_plan_returns_validated_plan() -> None:
    """B1: 模拟模型返回合法 step 集合时，draft_plan 返回通过校验的 AnalysisPlan"""
    payload = {
        "message": "建议先看销售分布，再做区域对比。",
        "steps": [
            {
                "title": "销量分布",
                "method": "describe",
                "target_columns": ["sales"], "rationale": "测试依据",
                "chart_type": "histogram",
                "params": {},
            }
        ],
    }
    agent, _ = _agent(payload)
    plan = agent.draft_plan(profile=_profile(), user_request="分析月度销量")
    assert isinstance(plan, AnalysisPlan)
    assert plan.message.startswith("建议")
    assert plan.steps[0].method == "describe"
    assert plan.steps[0].chart_type == "histogram"


def test_profile_injected_as_info() -> None:
    """B2: 数据画像以 JSON 摘要注入请求的 info 段"""
    payload = {"message": "ok", "steps": []}
    agent, fake = _agent(payload)
    agent.draft_plan(profile=_profile(), user_request="分析月度销量")
    assert fake.info_value is not None
    assert '"sales"' in fake.info_value
    assert '"row_count"' in fake.info_value


def test_invalid_method_rejected() -> None:
    """B3: 模拟模型返回非法 method 枚举时，宿主校验拒绝（pydantic ValidationError）"""
    payload = {
        "message": "ok",
        "steps": [
            {
                "title": "胡乱分析",
                "method": "magic",
                "target_columns": ["sales"], "rationale": "测试依据",
                "chart_type": "none",
            }
        ],
    }
    agent, _ = _agent(payload)
    with pytest.raises(ValidationError):
        agent.draft_plan(profile=_profile(), user_request="分析月度销量")


def test_revision_note_in_instruct() -> None:
    """B4: revision_note 非空时出现在请求 instruct 中"""
    payload = {"message": "ok", "steps": []}
    agent, fake = _agent(payload)
    agent.draft_plan(
        profile=_profile(),
        user_request="分析月度销量",
        revision_note="不要做时间序列预测",
    )
    assert fake.instruct_value is not None
    assert "不要做时间序列预测" in fake.instruct_value


def test_unknown_target_column_rejected() -> None:
    """B5: step 引用画像中不存在的列名时，宿主校验抛出 ValueError"""
    payload = {
        "message": "ok",
        "steps": [
            {
                "title": "列不存在",
                "method": "describe",
                "target_columns": ["not_a_column"], "rationale": "测试依据",
                "chart_type": "none",
            }
        ],
    }
    agent, _ = _agent(payload)
    with pytest.raises(ValueError, match="not_a_column"):
        agent.draft_plan(profile=_profile(), user_request="分析月度销量")


def test_tool_catalog_injected_into_info() -> None:
    """010: 模型 info 注入统计工具目录（含 group_compare 与必填参数）"""
    payload = {"message": "ok", "steps": []}
    agent, fake = _agent(payload)
    agent.draft_plan(profile=_profile(), user_request="分析")
    assert "group_compare" in fake.info_value
    assert "group_column" in fake.info_value


def test_missing_param_rejected_with_structured_issue() -> None:
    """010: 缺必填参数的计划在讨论阶段被拒绝（MISSING_PARAM），不进入执行"""
    from medsta.errors import ToolValidationError

    payload = {
        "message": "ok",
        "steps": [
            {
                "title": "两组比较",
                "method": "group_compare",
                "target_columns": ["sales"], "rationale": "测试依据",
                "chart_type": "boxplot",
                "params": {},
            }
        ],
    }
    agent, _ = _agent(payload)
    with pytest.raises(ToolValidationError) as excinfo:
        agent.draft_plan(profile=_profile(), user_request="比较两组销量")
    codes = {issue.code for issue in excinfo.value.issues}
    assert "MISSING_PARAM" in codes


def test_plan_options_default_confirm() -> None:
    """011: 模型未给 options 时宿主补默认 confirm 选项"""
    payload = {"message": "ok", "steps": []}
    agent, _ = _agent(payload)
    plan = agent.draft_plan(profile=_profile(), user_request="分析")
    assert any(option.action == "confirm" for option in plan.options)
    assert len({option.id for option in plan.options}) == len(plan.options)


def test_plan_options_deduplicated_and_validated() -> None:
    """011: 重复 option id 被去重，非法 action 由 pydantic 拒绝"""
    from pydantic import ValidationError as PydanticValidationError

    duplicate = {
        "message": "ok",
        "steps": [],
        "options": [
            {"id": "a", "label": "执行", "action": "confirm"},
            {"id": "a", "label": "再想", "action": "revise"},
        ],
    }
    agent, _ = _agent(duplicate)
    plan = agent.draft_plan(profile=_profile(), user_request="分析")
    assert len({option.id for option in plan.options}) == len(plan.options)

    invalid = {
        "message": "ok",
        "steps": [],
        "options": [{"id": "b", "label": "x", "action": "nonsense"}],
    }
    agent2, _ = _agent(invalid)
    with pytest.raises(PydanticValidationError):
        agent2.draft_plan(profile=_profile(), user_request="分析")

"""内置推荐工作链模板（recipe）与「AI 一键匹配」。

设计约束：
- 模板节点必须是注册表里的工具（否则用户载入后必然校验失败）；
- 占位槽位由宿主按类型/组数/取值筛候选，模型只在候选内做语义选择；
- 模型或候选缺失时回退规则匹配，并给出可读 warning（不静默产出非法链）。
"""
from __future__ import annotations

import pandas as pd

from medsta.agents.chain_recipes import (
    RECIPES,
    SLOT_LABELS,
    candidates_for,
    get_recipe,
    match_recipe,
    recipe_catalog,
)
from medsta.data.profiler import profile_dataframe
from medsta.stats.registry import HARD_ISSUE_CODES, all_tools, validate_step

CLINICAL_CSV = b"""group,value,age,shoushu,method,time,event
A,1.2,45,yes,open,12,0
A,2.4,52,yes,open,15,1
B,3.1,61,no,scope,9,0
B,3.8,58,no,scope,20,1
A,2.0,47,yes,open,18,0
B,3.4,63,no,scope,11,1
"""


def _df() -> pd.DataFrame:
    import io

    return pd.read_csv(io.BytesIO(CLINICAL_CSV))


def test_recipes_use_registered_tools_only() -> None:
    """模板节点必须是现有工具：否则「载入即失败」。"""
    names = {tool.name for tool in all_tools()}
    assert len(RECIPES) >= 4

    for recipe in RECIPES:
        assert recipe.title and recipe.description and recipe.skill
        for step in recipe.steps:
            assert step.method in names, f"{recipe.id} 使用了不存在的工具 {step.method}"


def test_slots_have_labels_and_candidates() -> None:
    """每个占位语义都要有中文标签与候选筛选规则。"""
    profile = profile_dataframe(_df())
    for recipe in RECIPES:
        for slot in recipe.slots():
            assert slot in SLOT_LABELS, slot
            assert isinstance(candidates_for(_df(), profile, slot), list)


def test_rule_match_produces_executable_steps() -> None:
    """规则匹配（无模型）：每步都通过宿主硬校验，且全部标为 rule。"""
    profile = profile_dataframe(_df())
    recipe = get_recipe("two_group_compare")
    assert recipe is not None

    result = match_recipe(recipe, _df(), profile)

    assert result.steps, "两组比较模板应能匹配出步骤"
    assert all(item["by"] == "rule" for item in result.matched)
    for step in result.steps:
        from medsta.agents.discussion import PlanStep

        issues = [
            issue
            for issue in validate_step(PlanStep.model_validate(step), _df())
            if issue.code in HARD_ISSUE_CODES
        ]
        assert issues == [], f"{step['title']} 未通过校验：{issues}"


def test_model_choice_accepted_only_when_in_candidates() -> None:
    """AI 选择：候选内被采纳（by=ai），候选外被丢弃并回退规则。"""
    profile = profile_dataframe(_df())
    recipe = get_recipe("two_group_compare")
    assert recipe is not None
    group_pool = candidates_for(_df(), profile, "group")
    assert len(group_pool) >= 2

    inside = match_recipe(recipe, _df(), profile, {"group": group_pool[1]})
    assert any(item["by"] == "ai" and item["column"] == group_pool[1] for item in inside.matched)

    outside = match_recipe(recipe, _df(), profile, {"group": "time"})  # time 在候选外
    assert all(item["by"] == "rule" for item in outside.matched)
    assert all(
        item["column"] != "time" for item in outside.matched if item["slot"] == "group"
    )


def test_missing_slot_skips_step_with_warning() -> None:
    """候选缺失：跳过该步并给出 warning，而不是产出非法链。"""
    small = pd.DataFrame({"value": [1.0, 2.0, 3.0]})
    profile = profile_dataframe(small)
    recipe = get_recipe("two_group_compare")
    assert recipe is not None

    result = match_recipe(recipe, small, profile)

    assert result.warnings
    assert any("缺少可用列" in warning for warning in result.warnings)
    assert all("group_column" not in step["params"] for step in result.steps)


def test_catalog_exposes_steps_and_slots() -> None:
    """目录接口数据：前端据此渲染推荐卡（含占位说明）。"""
    catalog = recipe_catalog()
    by_id = {item["id"]: item for item in catalog}

    assert "two_group_compare" in by_id
    entry = by_id["two_group_compare"]
    assert entry["slots"] and entry["slots"][0]["label"]
    assert all(step["method_available"] for step in entry["steps"])


# ---- 接口层 ----


class _AiAgentStub:
    """模拟模型：从服务端给的候选里挑最后一个（用来验证「候选内」被采纳）。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def match_chain_slots(self, *, recipe, candidates, profile):
        self.calls.append({"recipe": recipe.id, "candidates": candidates})
        return {
            slot: pool[-1]
            for slot, pool in candidates.items()
            if pool and slot != "feature_list"
        }


def _client_with_data(tmp_path):
    from fastapi.testclient import TestClient

    from medsta.app import create_app
    from medsta.session.manager import manager

    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    session_id = client.post("/sessions").json()["session_id"]
    upload = client.post(
        f"/sessions/{session_id}/data",
        files={"file": ("clinic.csv", CLINICAL_CSV, "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    return client, session_id


def test_builtin_recipes_endpoint(tmp_path) -> None:
    """GET /templates/builtin：推荐模板目录可匿名获取。"""
    from fastapi.testclient import TestClient

    from medsta.app import create_app

    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    response = client.get("/templates/builtin")

    assert response.status_code == 200
    recipes = response.json()["recipes"]
    assert recipes and all({"id", "title", "steps", "slots"} <= set(item) for item in recipes)


def test_match_endpoint_uses_ai_choices(tmp_path) -> None:
    """POST .../chain/match：模型从候选中挑列 → 返回可载入步骤并标注 ai。"""
    client, session_id = _client_with_data(tmp_path)
    stub = _AiAgentStub()
    client.app.state.service.set_agent(stub)

    response = client.post(
        f"/sessions/{session_id}/chain/match",
        json={"recipe_id": "two_group_compare", "use_ai": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ai"] is True
    assert stub.calls and stub.calls[0]["recipe"] == "two_group_compare"
    assert body["steps"]
    assert any(item["by"] == "ai" for item in body["matched"])


def test_match_endpoint_falls_back_without_model(tmp_path) -> None:
    """模型不可用：仍返回规则匹配结果（ai=false），不让「一键匹配」变成死路。"""
    client, session_id = _client_with_data(tmp_path)
    client.app.state.service.set_agent(None)

    response = client.post(
        f"/sessions/{session_id}/chain/match",
        json={"recipe_id": "quality_baseline", "use_ai": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ai"] is False
    assert body["steps"]
    assert all(item["by"] == "rule" for item in body["matched"])


def test_match_endpoint_rejects_unknown_recipe_and_missing_data(tmp_path) -> None:
    """未知模板 / 未上传数据 → 400（可读原因，不是 500）。"""
    client, session_id = _client_with_data(tmp_path)
    assert (
        client.post(
            f"/sessions/{session_id}/chain/match", json={"recipe_id": "nope"}
        ).status_code
        == 400
    )

    empty_client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(
        __import__("medsta.app", fromlist=["create_app"]).create_app(
            data_root=tmp_path / "sessions2"
        )
    )
    empty_session = empty_client.post("/sessions").json()["session_id"]
    response = empty_client.post(
        f"/sessions/{empty_session}/chain/match", json={"recipe_id": "quality_baseline"}
    )
    assert response.status_code == 400
    assert "数据" in response.json()["detail"]


def test_every_recipe_matches_into_executable_steps() -> None:
    """守护：每条内置模板在样例数据上匹配后，所有步骤都必须通过宿主硬校验。

    这条测试能捕获「模板用了 params-only 目标（logistic/生存）却被校验拒绝」这类
    注册表与模板不一致的问题——用户不该载入一条必然失败的推荐链。
    """
    from medsta.agents.discussion import PlanStep
    from medsta.stats.registry import HARD_ISSUE_CODES, validate_step

    df = _df()
    profile = profile_dataframe(df)
    for recipe in RECIPES:
        result = match_recipe(recipe, df, profile)
        assert result.steps, f"{recipe.id} 未匹配出任何步骤（数据应覆盖其占位）"
        for step in result.steps:
            issues = [
                issue
                for issue in validate_step(PlanStep.model_validate(step), df)
                if issue.code in HARD_ISSUE_CODES
            ]
            assert issues == [], f"{recipe.id} 的「{step['title']}」不可执行：{issues}"

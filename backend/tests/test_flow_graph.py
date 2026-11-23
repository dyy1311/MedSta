"""047 流程图方案：steps + depends_on → 节点/边/拓扑序/mermaid。

方案以流程图交付确认：节点必须是注册表里的工具，缺省依赖降级为线性链
（模型漏填不是错误，图始终可执行）。
"""
from __future__ import annotations

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.agents.flow import plan_flow


def _plan(*deps: list[int]) -> AnalysisPlan:
    steps = []
    for index, depends_on in enumerate(deps):
        steps.append(
            PlanStep(
                title=f"步骤{index + 1}",
                method="describe" if index % 2 == 0 else "group_compare",
                target_columns=["value"],
                chart_type="none",
                params={} if index % 2 == 0 else {"group_column": "group"},
                rationale="测试依据",
                depends_on=depends_on,
            )
        )
    return AnalysisPlan(message="方案", steps=steps)


def test_default_dependency_is_linear_chain() -> None:
    """B1: 未声明 depends_on → 宿主补成线性链（0→1→2）。"""
    flow = plan_flow(_plan([], [], []))

    assert [node["depends_on"] for node in flow["nodes"]] == [[], [0], [1]]
    assert flow["edges"] == [{"from": 0, "to": 1}, {"from": 1, "to": 2}]
    assert flow["order"] == [0, 1, 2]


def test_explicit_dependency_preserved() -> None:
    """B1: 显式依赖（分支汇合）保留：节点 2 同时依赖 0 与 1。"""
    flow = plan_flow(_plan([], [], [0, 1]))

    assert flow["nodes"][2]["depends_on"] == [0, 1]
    assert {"from": 0, "to": 2} in flow["edges"]
    assert {"from": 1, "to": 2} in flow["edges"]
    assert flow["order"] == [0, 1, 2]


def test_invalid_dependency_degrades_not_crashes() -> None:
    """B1: 越界/自环/反向依赖被忽略并降级为线性链。"""
    flow = plan_flow(_plan([], [5], [2, -1, 0]))

    assert flow["nodes"][1]["depends_on"] == [0]  # 越界 → 线性
    assert flow["nodes"][2]["depends_on"] == [0]  # 自环与负数被丢弃，保留 0
    assert all(edge["from"] < edge["to"] for edge in flow["edges"])


def test_nodes_expose_tool_and_params() -> None:
    """B1: 节点带工具名/目标列/参数，用户可核对「用的是现有工具」。"""
    flow = plan_flow(_plan([], [0]))
    node = flow["nodes"][1]

    assert node["method"] == "group_compare"
    assert node["target_columns"] == ["value"]
    assert node["params"] == {"group_column": "group"}
    assert node["id"] == "step_2"


def test_mermaid_is_flowchart_text() -> None:
    """B1: mermaid 文本包含节点与边（前端可复制/渲染）。"""
    flow = plan_flow(_plan([], [0]))

    assert flow["mermaid"].startswith("flowchart TD")
    assert 'n0["1. 步骤1<br/>describe"]' in flow["mermaid"]
    assert "n0 --> n1" in flow["mermaid"]


def test_empty_plan_is_empty_flow() -> None:
    """B1: 空方案不产出悬空边。"""
    flow = plan_flow(AnalysisPlan(message="空", steps=[]))

    assert flow["nodes"] == [] and flow["edges"] == [] and flow["order"] == []


def test_plan_event_carries_flow(tmp_path) -> None:
    """B2: chat 下发的 plan 事件带 flow（节点/边/mermaid），旧字段保持兼容。"""
    from fastapi.testclient import TestClient

    from medsta.app import create_app
    from medsta.session.manager import manager
    from tests.helpers import collect_until, fake_agent, upload_csv

    two_step_plan = {
        "message": "先描述分布，再比较两组",
        "steps": [
            {
                "title": "分布统计",
                "method": "describe",
                "target_columns": ["value"],
                "chart_type": "none",
                "params": {},
                "rationale": "先看分布形态",
            },
            {
                "title": "组间比较",
                "method": "group_compare",
                "target_columns": ["value"],
                "chart_type": "none",
                "params": {"group_column": "group"},
                "rationale": "两组连续变量比较",
                "depends_on": [0],
            },
        ],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }

    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    client.app.state.service.set_agent(fake_agent(two_step_plan))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value 的分布"})
        _, review = collect_until(ws, {"type_review"})
        assert review["type"] == "type_review"
        ws.send_json(
            {
                "type": "type_confirm",
                "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
            }
        )
        _, plan = collect_until(ws, {"plan"})

    assert plan["steps"], "plan 事件仍带 steps（旧客户端兼容）"
    flow = plan["flow"]
    assert [node["method"] for node in flow["nodes"]] == [
        step["method"] for step in plan["steps"]
    ]
    assert flow["mermaid"].startswith("flowchart TD")
    assert flow["edges"], "多节点方案应有依赖边"

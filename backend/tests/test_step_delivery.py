"""047 逐节点交付：每个工作节点完成即交付，失败只影响该节点。

用户痛点：整条链一次报错就得全部重来。现在节点级隔离 + 节点级交付，
失败节点可单独 retry/amend，其余节点结果不丢。
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from medsta.agents.discussion import AnalysisPlan, PlanStep
from medsta.app import create_app
from medsta.pipeline.executor import PipelineExecutor
from medsta.session.manager import manager
from tests.helpers import CSV, collect_until, fake_agent, upload_csv

TWO_STEP_PLAN = {
    "message": "先描述，再比较",
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


def _df() -> pd.DataFrame:
    import io

    return pd.read_csv(io.BytesIO(CSV))


def _plan_with_failing_step() -> AnalysisPlan:
    return AnalysisPlan(
        message="第二步必然失败",
        steps=[
            PlanStep(
                title="分布统计",
                method="describe",
                target_columns=["value"],
                chart_type="none",
                params={},
                rationale="先看分布",
            ),
            PlanStep(
                title="坏掉的比较",
                method="group_compare",
                target_columns=["value"],
                chart_type="none",
                # 分组列只有 2 组但这里指定不存在列会先被校验拦住，
                # 故用「配对」参数让执行期抛错（数据非配对）
                params={"group_column": "group", "paired": True},
                rationale="故意构造执行期失败",
            ),
        ],
    )


def test_executor_reports_each_step(tmp_path, monkeypatch) -> None:
    """B3: 成功与失败节点都回调；失败不阻断后续（报告仍有两步）。"""
    import medsta.pipeline.executor as executor_module

    real = executor_module.execute_step_with_frame

    def flaky(df, step, artifact_dir, index):
        if index == 1:
            raise RuntimeError("模拟第二节点运行期失败")
        return real(df, step, artifact_dir, index)

    monkeypatch.setattr(executor_module, "execute_step_with_frame", flaky)
    seen: list[dict] = []
    plan = _plan_with_failing_step()

    report = PipelineExecutor().execute(
        _df(),
        plan,
        tmp_path,
        on_step_result=lambda index, total, payload: seen.append(payload),
    )

    assert [item["index"] for item in seen] == [0, 1]
    assert seen[0]["status"] == "success"
    assert seen[1]["status"] == "failed"
    assert seen[1]["error"]["message"].startswith("模拟第二节点")
    assert len(report.steps) == 2  # 失败节点仍占位，报告不丢前半段
    assert all(item["total"] == 2 for item in seen)


def test_step_result_frames_streamed(tmp_path) -> None:
    """B4: 执行期下发 step_result 帧（含 index/total/step 结果），早于 review_request。"""
    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    client.app.state.service.set_agent(fake_agent(TWO_STEP_PLAN))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    with client.websocket_connect(f"/ws/{session_id}") as ws:
        ws.send_json({"type": "chat", "content": "分析 value 并按 group 比较"})
        collect_until(ws, {"type_review"})
        ws.send_json(
            {
                "type": "type_confirm",
                "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
            }
        )
        collect_until(ws, {"plan"})
        ws.send_json({"type": "confirm_plan"})
        frames, _ = collect_until(ws, {"chart_config", "review_request"})
        if frames and frames[-1].get("type") == "chart_config":
            ws.send_json(
                {
                    "type": "chart_choice",
                    "use_default": True,
                    "layout": "separate",
                    "alpha": 0.05,
                    "correction": "holm",
                }
            )
            frames, _ = collect_until(ws, {"review_request"})

    step_frames = [frame for frame in frames if frame.get("type") == "step_result"]
    assert [frame["index"] for frame in step_frames] == [0, 1]
    assert all(frame["total"] == 2 for frame in step_frames)
    assert step_frames[0]["step"]["status"] == "success"
    assert step_frames[0]["step"]["title"] == "分布统计"
    # 节点交付必须早于最终审阅请求
    types = [frame.get("type") for frame in frames]
    assert types.index("step_result") < types.index("review_request")


def _drive_to_review(client, session_id):
    from medsta.session.manager import manager as mgr

    mgr.get(session_id)
    ws = client.websocket_connect(f"/ws/{session_id}")
    conn = ws.__enter__()
    conn.send_json({"type": "chat", "content": "分析 value 并按 group 比较"})
    collect_until(conn, {"type_review"})
    conn.send_json(
        {
            "type": "type_confirm",
            "types": {"group": "categorical", "value": "continuous", "age": "continuous"},
        }
    )
    collect_until(conn, {"plan"})
    conn.send_json({"type": "confirm_plan"})
    frames, _ = collect_until(conn, {"chart_config", "review_request"})
    if frames and frames[-1].get("type") == "chart_config":
        conn.send_json(
            {
                "type": "chart_choice",
                "use_default": True,
                "layout": "separate",
                "alpha": 0.05,
                "correction": "holm",
            }
        )
        collect_until(conn, {"review_request"})
    return ws, conn


def test_retry_step_reruns_node_and_downstream(tmp_path) -> None:
    """B6: 失败节点可单独重试（含下游），逐节点交付更新后的结果。"""
    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(TWO_STEP_PLAN))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    ws, conn = _drive_to_review(client, session_id)
    try:
        # 人为把一个已成功节点改成失败（模拟执行期报错后的状态）
        service._reports[session_id]["steps"][1] = {
            "title": "组间比较",
            "method": "group_compare",
            "status": "failed",
            "error": {"code": "EXECUTION_FAILED", "message": "模拟失败", "hint": ""},
        }

        conn.send_json({"type": "retry_step", "index": 1})
        frames, _ = collect_until(conn, {"review_request"})

        step_frames = [f for f in frames if f.get("type") == "step_result"]
        assert step_frames, "重试必须逐节点交付"
        assert step_frames[0]["index"] == 1
        assert step_frames[0]["step"]["status"] == "success"
        assert step_frames[0]["step"]["updated"] is True
        assert service._reports[session_id]["steps"][1]["status"] == "success"
    finally:
        ws.__exit__(None, None, None)


def test_retry_step_rejects_bad_index(tmp_path) -> None:
    """B6: 越界序号返回 INVALID_PARAM，不动报告。"""
    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(TWO_STEP_PLAN))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    ws, conn = _drive_to_review(client, session_id)
    try:
        conn.send_json({"type": "retry_step", "index": 99})
        frames, error = collect_until(conn, {"error"})
        assert error["code"] == "INVALID_PARAM"
    finally:
        ws.__exit__(None, None, None)


class _AmendAgent:
    """定点修正替身：记录收到的上下文，返回修正后的单节点方案。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def amend_step(self, *, profile, plan, index, error, note, context=""):
        from medsta.agents.discussion import PlanStep

        self.calls.append(
            {
                "index": index,
                "error": error,
                "note": note,
                "context": context,
                "titles": [s.title for s in plan.steps],
            }
        )
        return PlanStep(
            title="组间比较（已修正）",
            method="group_compare",
            target_columns=["value"],
            chart_type="none",
            params={"group_column": "group"},
            rationale="按用户补充：用 group 分组比较 value",
        )


def test_amend_step_reruns_node_with_context(tmp_path) -> None:
    """B7: amend_step 把「图 + 该节点 + 错误 + 用户补充」交给模型，修正后重跑该节点。"""
    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(TWO_STEP_PLAN))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    ws, conn = _drive_to_review(client, session_id)
    try:
        agent = _AmendAgent()
        service.set_agent(agent)
        service._reports[session_id]["steps"][1] = {
            "title": "组间比较",
            "method": "group_compare",
            "status": "failed",
            "error": {"code": "EXECUTION_FAILED", "message": "分组列不是 group", "hint": ""},
        }

        conn.send_json({"type": "amend_step", "index": 1, "note": "按 group 分组比较 value"})
        frames, _ = collect_until(conn, {"review_request"})

        assert agent.calls and agent.calls[0]["index"] == 1
        assert agent.calls[0]["note"] == "按 group 分组比较 value"
        assert "分组列不是 group" in str(agent.calls[0]["error"])
        # 模型拿到的是「修正前的完整工作流」，据此只改这一个节点
        assert agent.calls[0]["titles"] == ["分布统计", "组间比较"]
        # 会话上下文（节点进度）随补充信息一并注入，模型才知道改到哪一步
        assert "已确认工作流" in agent.calls[0]["context"]

        plan_frames = [f for f in frames if f.get("type") == "plan"]
        assert plan_frames and plan_frames[0]["flow"]["nodes"]
        assert plan_frames[0]["steps"][1]["title"] == "组间比较（已修正）"

        step_frames = [f for f in frames if f.get("type") == "step_result"]
        assert step_frames and step_frames[0]["step"]["status"] == "success"
        # 依赖关系保持原样（修正不打乱图结构）
        assert service._plans[session_id].steps[1].depends_on == [0]
    finally:
        ws.__exit__(None, None, None)


def test_retry_replays_upstream_frame_and_clears_stale_error(tmp_path) -> None:
    """重跑下游必须用上游清洗后的表，并清掉上下文里过期的失败记录。"""
    from medsta.session.context import NODE_DONE, NODE_FAILED

    manager.clear()
    plan = {
        "message": "先标准化再描述",
        "steps": [
            {
                "title": "标准化",
                "method": "standardize",
                "target_columns": ["value"],
                "chart_type": "none",
                "params": {"method": "zscore"},
                "rationale": "先把 value 变成标准分",
            },
            {
                "title": "分布统计",
                "method": "describe",
                "target_columns": ["value"],
                "chart_type": "none",
                "params": {},
                "rationale": "看标准化后的分布",
                "depends_on": [0],
            },
        ],
        "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
    }
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(plan))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    ws, conn = _drive_to_review(client, session_id)
    try:
        first = service._reports[session_id]["steps"][1]["result"]["stats"]["value"]["mean"]
        assert first == pytest.approx(0.0, abs=1e-6)

        context = service._contexts.find(session_id)
        assert context is not None
        context.mark_node(1, NODE_FAILED, {"message": "过期失败"})

        conn.send_json({"type": "retry_step", "index": 1})
        collect_until(conn, {"review_request"})

        again = service._reports[session_id]["steps"][1]["result"]["stats"]["value"]["mean"]
        # 原始 value 均值是 4；若没重放标准化，这里会回到 4
        assert again == pytest.approx(0.0, abs=1e-6)
        assert context.node_states[1] == NODE_DONE
        assert 1 not in context.node_errors
    finally:
        ws.__exit__(None, None, None)


def test_amend_step_without_model_reports_unavailable(tmp_path) -> None:
    """B7: 模型未配置时明确报 MODEL_UNAVAILABLE，不改动方案。"""
    manager.clear()
    client = TestClient(create_app(data_root=tmp_path / "sessions"))
    service = client.app.state.service
    service.set_agent(fake_agent(TWO_STEP_PLAN))
    session_id = client.post("/sessions").json()["session_id"]
    upload_csv(client, session_id)

    ws, conn = _drive_to_review(client, session_id)
    try:
        service.set_agent(None)
        conn.send_json({"type": "amend_step", "index": 1, "note": "改一下"})
        _, error = collect_until(conn, {"error"})
        assert error["code"] == "MODEL_UNAVAILABLE"
    finally:
        ws.__exit__(None, None, None)

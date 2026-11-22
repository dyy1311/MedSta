"""Pipeline 执行器：按 AnalysisPlan 顺序派发统计工具。

执行态无模型参与——工具契约与实现在 stats/registry.py（单一真相源）；
本模块只负责：计划级校验（失败即拒绝）、逐步执行、单步失败隔离、报告汇总。
"""
from __future__ import annotations

import pathlib
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from medsta.agents.discussion import AnalysisPlan
from medsta.errors import ErrorCode, ToolValidationError
from medsta.stats.registry import HARD_ISSUE_CODES, execute_step_with_frame, validate_plan


class StepResult(BaseModel):
    title: str
    method: str
    status: Literal["success", "failed"] = "success"  # type: ignore[valid-type]
    result: dict[str, Any] = Field(default_factory=dict)
    artifact: str | None = None
    table: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class ExecutionReport(BaseModel):
    steps: list[StepResult] = Field(default_factory=list)

    @property
    def all_success(self) -> bool:
        return all(s.status == "success" for s in self.steps)


def _jsonify(value: Any) -> Any:
    """把 numpy/pandas 值转为 JSON 兼容类型。

    NaN/Inf → None；numpy 标量（含 np.bool_，它不是 Python bool 的子类）
    统一走 `.item()` 或显式转换——漏转会让 websocket.send_json 抛 TypeError，
    整帧 review_request 发不出去，前端永远停在「执行中」。
    """
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        # NaN/±Inf 一律归一为 null：JSON 无对应字面量（浏览器 JSON.parse 直接失败）
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [_jsonify(v) for v in value.tolist()]
    if isinstance(value, np.datetime64):
        return None if pd.isna(value) else str(value)
    if isinstance(value, np.generic):
        return _jsonify(value.item())
    if value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return None if pd.isna(value) else str(value)
    return value


def execute_node(
    df: pd.DataFrame, step: Any, artifact_dir: str | pathlib.Path, index: int
) -> tuple[dict, Any]:
    """执行单个节点（047 重试/定点修正复用）：返回 (节点结果 dict, 链间 DataFrame)。

    失败不外抛，返回 status=failed 的结果——调用方据 status 交付并决定是否继续。
    """
    try:
        result, artifact, next_frame = execute_step_with_frame(df, step, artifact_dir, index)
        payload = {
            "title": step.title,
            "method": step.method,
            "status": "success",
            "result": _jsonify(result),
            "artifact": artifact,
            "table": _jsonify(result.get("table")),
        }
        return payload, next_frame
    except Exception as exc:  # 单节点失败不阻断后续节点
        return (
            {
                "title": step.title,
                "method": step.method,
                "status": "failed",
                "error": {
                    "code": ErrorCode.EXECUTION_FAILED.value,
                    "message": str(exc),
                    "hint": "检查该步骤的参数取值与数据分布（样本量、组数、缺失）",
                },
            },
            None,
        )


class PipelineExecutor:
    """按 plan 顺序执行步骤：硬校验失败抛 ToolValidationError，运行期单步失败隔离。"""

    def execute(
        self,
        df: pd.DataFrame,
        plan: AnalysisPlan,
        artifact_dir: str | pathlib.Path,
        on_step: Any = None,
        on_step_result: Any = None,
    ) -> ExecutionReport:
        issues = validate_plan(plan, df)
        hard_issues = [issue for issue in issues if issue.code in HARD_ISSUE_CODES]
        if hard_issues:
            raise ToolValidationError(hard_issues)

        artifact_dir = pathlib.Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report = ExecutionReport()
        total = len(plan.steps)
        shared_paths: list[tuple[int, pathlib.Path]] = []

        def emit_step_result(index: int, *, updated: bool = False) -> None:
            """单节点交付：每步完成立即回调（失败节点同样交付，不阻断后续）。"""
            if on_step_result is None:
                return
            payload = report.steps[index].model_dump()
            payload["index"] = index
            payload["total"] = total
            payload["updated"] = updated
            on_step_result(index, total, payload)
        for index, step in enumerate(plan.steps):
            if on_step is not None:
                on_step(index, total, step.title)
            try:
                # 037 链间管道：数据产出型工具（如 impute）的插补后 DataFrame
                # 供同链后续步骤使用；_next_frame 在 registry 入口剥离（不进报告）
                result, artifact, next_frame = execute_step_with_frame(
                    df, step, artifact_dir, index
                )
                if next_frame is not None:
                    df = next_frame
                if artifact and step.params.get("_layout") == "shared":
                    shared_paths.append((index, artifact_dir / artifact))
                report.steps.append(
                    StepResult(
                        title=step.title,
                        method=step.method,
                        status="success",
                        result=_jsonify(result),
                        artifact=artifact,
                        # 表格同样过一遍 JSON 归一：NaN/numpy 标量若原样下发，
                        # 前端 JSON.parse 会整帧失败（表格与图表一起消失）
                        table=_jsonify(result.get("table")),
                    )
                )
                emit_step_result(index)
            except Exception as exc:  # 单步失败不拖垮整份报告
                report.steps.append(
                    StepResult(
                        title=step.title,
                        method=step.method,
                        status="failed",
                        error={
                            "code": ErrorCode.EXECUTION_FAILED.value,
                            "message": str(exc),
                            "hint": "检查该步骤的参数取值与数据分布（样本量、组数、缺失）",
                        },
                    )
                )
                emit_step_result(index)
        if len(shared_paths) >= 2:
            from medsta.stats.plotting import render_combined

            combined = render_combined([path for _, path in shared_paths], artifact_dir)
            for index, _ in shared_paths:
                report.steps[index].artifact = combined.name
                report.steps[index].result["artifact"] = combined.name
                emit_step_result(index, updated=True)  # 拼图替换了原图，节点结果需再交付一次
        return report

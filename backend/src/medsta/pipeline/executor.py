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
from medsta.stats.registry import HARD_ISSUE_CODES, execute_step, validate_plan


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
    """把 numpy/pandas 值转为 JSON 兼容类型。"""
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, np.ndarray):
        return [_jsonify(v) for v in value.tolist()]
    return value


class PipelineExecutor:
    """按 plan 顺序执行步骤：硬校验失败抛 ToolValidationError，运行期单步失败隔离。"""

    def execute(
        self,
        df: pd.DataFrame,
        plan: AnalysisPlan,
        artifact_dir: str | pathlib.Path,
        on_step: Any = None,
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
        for index, step in enumerate(plan.steps):
            if on_step is not None:
                on_step(index, total, step.title)
            try:
                result, artifact = execute_step(df, step, artifact_dir, index)
                if artifact and step.params.get("_layout") == "shared":
                    shared_paths.append((index, artifact_dir / artifact))
                report.steps.append(
                    StepResult(
                        title=step.title,
                        method=step.method,
                        status="success",
                        result=_jsonify(result),
                        artifact=artifact,
                        table=result.get("table"),
                    )
                )
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
        if len(shared_paths) >= 2:
            from medsta.stats.plotting import render_combined

            combined = render_combined([path for _, path in shared_paths], artifact_dir)
            for index, _ in shared_paths:
                report.steps[index].artifact = combined.name
                report.steps[index].result["artifact"] = combined.name
        return report

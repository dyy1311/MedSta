"""统计方案流程图：`steps[].depends_on` → 节点/边/mermaid 文本。

方案以「流程图」交付给用户确认：节点即工作节点（必须是注册表里的工具），
边即执行依赖。依赖只允许指向更早的节点（避免环），缺省时降级为线性链——
模型漏填 `depends_on` 不是错误，宿主补全即可（图始终可执行）。
"""
from __future__ import annotations

from typing import Any


def _coerce_deps(raw: Any, index: int) -> list[int]:
    deps: list[int] = []
    for item in raw or []:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        # 只接受「更早的节点」：自环、反向、越界一律忽略（降级为线性链）
        if 0 <= value < index and value not in deps:
            deps.append(value)
    return deps


def _topological_order(nodes: list[dict]) -> list[int]:
    """依赖优先的稳定拓扑序（同层按索引升序）。"""
    remaining = {node["index"]: set(node["depends_on"]) for node in nodes}
    order: list[int] = []
    while remaining:
        ready = sorted(index for index, deps in remaining.items() if deps <= set(order))
        if not ready:  # 理论上不会发生（依赖已过滤为前序）
            order.extend(sorted(remaining))
            break
        index = ready[0]
        order.append(index)
        remaining.pop(index)
    return order


def _mermaid(nodes: list[dict], edges: list[dict]) -> str:
    lines = ["flowchart TD"]
    for node in nodes:
        title = str(node["title"]).replace('"', "'")
        method = str(node["method"])
        label = f'{node["index"] + 1}. {title}<br/>{method}'
        lines.append(f'  n{node["index"]}["{label}"]')
    for edge in edges:
        lines.append(f'  n{edge["from"]} --> n{edge["to"]}')
    if not edges and len(nodes) > 1:  # 防御：图至少连通
        for index in range(len(nodes) - 1):
            lines.append(f"  n{index} --> n{index + 1}")
    return "\n".join(lines)


def plan_flow(plan: Any) -> dict:
    """把方案转成流程图（节点/边/拓扑序/mermaid 文本），供 plan 事件与上下文使用。"""
    steps = list(getattr(plan, "steps", []) or [])
    nodes: list[dict] = []
    edges: list[dict] = []
    for index, step in enumerate(steps):
        deps = _coerce_deps(getattr(step, "depends_on", None), index)
        if not deps and index > 0:
            deps = [index - 1]  # 缺省依赖：接在上一步之后
        nodes.append(
            {
                "index": index,
                "id": getattr(step, "step_id", None) or f"step_{index + 1}",
                "title": str(getattr(step, "title", f"步骤 {index + 1}")),
                "method": str(getattr(step, "method", "")),
                "target_columns": [str(column) for column in getattr(step, "target_columns", [])],
                "params": dict(getattr(step, "params", {}) or {}),
                "chart_type": str(getattr(step, "chart_type", "none")),
                "rationale": str(getattr(step, "rationale", "") or ""),
                "depends_on": deps,
            }
        )
        edges.extend({"from": dep, "to": index} for dep in deps)
    return {
        "nodes": nodes,
        "edges": edges,
        "order": _topological_order(nodes),
        "mermaid": _mermaid(nodes, edges),
    }

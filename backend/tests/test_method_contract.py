"""023 B16：模型方法枚举与注册表必须来自同一真相源。

`MethodType` 是 pydantic 输出契约的一部分：注册表里有、Literal 里没有的方法，
模型一旦选中就会在 schema 校验阶段被拒（不会走到宿主 validate_step 的友好提示）。
本用例把这种漂移变成确定性失败。
"""
from __future__ import annotations

from typing import get_args

from medsta.agents.discussion import ChartType, MethodType
from medsta.stats import registry


def test_method_literal_matches_registry() -> None:
    literal = set(get_args(MethodType))
    registered = {spec.name for spec in registry.all_tools()} | set(registry.ALIASES)

    assert literal == registered, {
        "missing_in_literal": sorted(registered - literal),
        "missing_in_registry": sorted(literal - registered),
    }


def test_chart_literal_matches_registry() -> None:
    """图表枚举与 CHART_TYPES 同源：漏改会让新图表在 pydantic 阶段被拒。"""
    literal = set(get_args(ChartType))
    registered = set(registry.CHART_TYPES)

    assert literal == registered, {
        "missing_in_literal": sorted(registered - literal),
        "missing_in_registry": sorted(literal - registered),
    }

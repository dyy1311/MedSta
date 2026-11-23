"""031 B1–B6：文档与代码的一致性约束。

文档漂移比没有文档更危险：README 曾长期停在「12 类方法 / 后端 200 项」，
而实际已是 22 类。这些断言把「文档必须与注册表同源」变成可执行的规则。
"""
from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ARCH = REPO_ROOT / "docs" / "architecture.md"
GUIDE = REPO_ROOT / "docs" / "product-guide.md"
STATS = REPO_ROOT / "docs" / "statistics-methods.md"
README = REPO_ROOT / "README.md"

# 允许出现在 README 的易过期表述之外的内容；此处只禁「具体计数」。
_VOLATILE_COUNT = re.compile(r"\d+\s*(项\b|passed|类统计方法)")
_MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
_EDGE = re.compile(r"-->|->>|-->>|==>")


def _read(path: pathlib.Path) -> str:
    assert path.exists(), f"文档尚未创建：{path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def _registered_tools() -> set[str]:
    from medsta.stats import registry

    return {spec.name for spec in registry.all_tools()}


def _appendix_tools(text: str) -> set[str]:
    """解析「## 附录 A」小节表格首列反引号内的工具名。"""
    marker = "## 附录 A"
    assert marker in text, "architecture.md 缺少「附录 A 工具清单」"
    section = text.split(marker, 1)[1]
    section = section.split("\n## ", 1)[0]
    return set(re.findall(r"^\|\s*`([a-z_]+)`", section, re.M))


def test_appendix_tools_match_registry() -> None:
    """B1: 附录工具清单必须与注册表严格相等（多/少/拼错都失败）。"""
    listed = _appendix_tools(_read(ARCH))
    registered = _registered_tools()

    assert listed == registered, {
        "missing_in_doc": sorted(registered - listed),
        "extra_in_doc": sorted(listed - registered),
    }


def test_readme_has_no_volatile_counts() -> None:
    """B2: README 不写具体测试计数或方法类数，避免再次过期。"""
    offenders = _VOLATILE_COUNT.findall(_read(README))

    assert offenders == [], f"README 出现易过期计数：{offenders}"


def test_doc_links_resolve() -> None:
    """B3: 文档中的相对链接必须指向真实文件。"""
    broken: list[str] = []
    for path in (README, ARCH, GUIDE, STATS):
        text = _read(path)
        for target in re.findall(r"\]\(([^)#:]+?)\)", text):
            if target.startswith(("http", "mailto")):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.exists():
                broken.append(f"{path.name} -> {target}")

    assert broken == []


def test_product_guide_covers_all_tools() -> None:
    """B4: 产品说明的能力矩阵必须覆盖全部工具。"""
    text = _read(GUIDE)
    missing = [name for name in sorted(_registered_tools()) if f"`{name}`" not in text]

    assert missing == [], f"product-guide 未覆盖：{missing}"


def test_architecture_has_three_non_trivial_diagrams() -> None:
    """B5: 三张图存在，且每张至少 10 条边（拦截空图/骨架图）。"""
    blocks = _MERMAID.findall(_read(ARCH))

    assert len(blocks) == 3, f"应有 3 张 Mermaid 图，实际 {len(blocks)}"
    for index, block in enumerate(blocks, start=1):
        edges = len(_EDGE.findall(block))
        assert edges >= 10, f"第 {index} 张图仅 {edges} 条边，疑似骨架图"


@pytest.mark.parametrize("phrase", ["12 类统计方法", "后端 200 项", "前端 35 项"])
def test_no_deprecated_phrasing(phrase: str) -> None:
    """B6: 已过期的表述不得复发。"""
    for path in (README, ARCH, GUIDE, STATS):
        assert phrase not in _read(path), f"{path.name} 仍含过期表述「{phrase}」"


def test_appendix_b_states_match_session_status() -> None:
    """B8(审查): 附录 B 状态表与 SessionStatus 枚举严格同源。

    架构文档曾长期列出代码中不存在的 AWAITING_REVIEW（漂移检测不到），此断言封堵。
    """
    from medsta.session.manager import SessionStatus

    section = _read(ARCH).split("## 附录 B", 1)[1]
    states_part = section.split("状态（`SessionStatus`）", 1)[1]
    listed = {match.lower() for match in re.findall(r"^\|\s*`([A-Za-z_]+)`\s*\|", states_part, re.M)}
    actual = {status.value for status in SessionStatus}

    assert listed == actual, {
        "missing_in_doc": sorted(actual - listed),
        "extra_in_doc": sorted(listed - actual),
    }


def test_appendix_b_covers_emitted_ws_events() -> None:
    """B9(审查): 附录 B 事件表 ⊇ service/ws 实际下发的出站事件类型。"""
    from medsta.session.service import USER_ACTION_EVENTS

    emitted: set[str] = set()
    for rel in ("backend/src/medsta/session/service.py", "backend/src/medsta/api/ws.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        emitted.update(re.findall(r'"type":\s*"([a-z_]+)"', text))
    inbound = USER_ACTION_EVENTS | {"workspace", "resume", "suggest_column_types"}
    section = _read(ARCH).split("## 附录 B", 1)[1].split("状态（`SessionStatus`）", 1)[0]
    listed = set(re.findall(r"`([a-z_]+)`", section))

    missing = sorted(event for event in emitted - listed - inbound if not event.endswith("_user"))
    assert missing == [], f"附录 B 缺事件：{missing}"


def test_tools_md_matches_registry() -> None:
    """B7(033): tools.md 双向登记全部统计工具与作图类型，不得缺漏或含已注销工具。"""
    tools_md = REPO_ROOT / "docs" / "tools.md"
    text = _read(tools_md)

    marker = "## 统计工具"
    assert marker in text, "tools.md 缺少「统计工具」小节"
    tool_section = text.split(marker, 1)[1].split("\n## ", 1)[0]
    listed = set(re.findall(r"^\|\s*`([a-z_]+)`", tool_section, re.M))
    missing = sorted(_registered_tools() - listed)
    stale = sorted(listed - _registered_tools())
    assert missing == [], f"tools.md 缺登记工具：{missing}"
    assert stale == [], f"tools.md 含已注销工具：{stale}"

    from medsta.stats.plotting import CHART_LABELS
    from medsta.stats.registry import CHART_TYPES

    for chart in CHART_TYPES:
        if chart == "none":
            continue
        assert f"`{chart}`" in text, f"tools.md 缺作图类型：{chart}"
        assert CHART_LABELS.get(chart, chart) in text, f"tools.md 缺图表中文名：{chart}"

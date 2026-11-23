"""047 内置统计 skills：SAMPL 报告规范 + 检验选择决策树 + 常见误用的可注入知识。

宿主只做关键词挑选与长度裁剪（确定性），语义判断留给模型；
这里守护「条目完整、挑得准、注入有界」三件事。
"""
from __future__ import annotations

import pandas as pd

from medsta.agents.stats_skills import (
    SKILLS,
    select_skills,
    skills_for_request,
)
from medsta.data.profiler import profile_dataframe


def test_every_skill_is_complete() -> None:
    """B10: 每条 skill 必须有适用场景、至少两条硬规则、至少一条报告要求。"""
    assert len(SKILLS) >= 10
    keys = [skill.key for skill in SKILLS]
    assert len(keys) == len(set(keys)), "skill key 必须唯一"

    for skill in SKILLS:
        assert skill.title and skill.when
        assert len(skill.rules) >= 2, skill.key
        assert skill.reporting, skill.key
        assert skill.pitfalls, skill.key
        assert skill.keywords, skill.key


def test_select_skills_by_request_keywords() -> None:
    """B10: 诉求关键词决定注入哪几条（生存/缺失/多组/两组各自命中）。"""
    survival = {skill.key for skill in select_skills("比较两组患者的总生存期与复发情况")}
    assert "survival" in survival

    missing = {skill.key for skill in select_skills("数据缺失很多，要不要插补")}
    assert "missing_data" in missing

    multi = {skill.key for skill in select_skills("三组之间的方差分析怎么做")}
    assert "continuous_multi_group" in multi


def test_select_skills_falls_back_to_reporting() -> None:
    """B10: 无关键词时给通用约束（报告规范 + 缺失数据），而不是空注入。"""
    picked = {skill.key for skill in select_skills("帮我看看这个数据")}
    assert "reporting_sampl" in picked


def test_digest_is_bounded() -> None:
    """B10: 注入长度受限（不能挤占画像与工具目录）。"""
    text = skills_for_request("生存分析 缺失 多重比较 样本量 配对 相关 回归 卡方", limit=12)
    assert len(text) <= 1400
    assert "\n- " in text or text.startswith("- ")


def test_prompt_injects_skills() -> None:
    """B10: 讨论 prompt 的 info 段带上方法学要点（模型据此选方法与填参数）。"""
    from medsta.agents.discussion import DiscussionAgent

    captured: dict[str, str] = {}

    class RecordingRequest:
        def input(self, value):
            return self

        def info(self, value):
            captured["info"] = value
            return self

        def instruct(self, value):
            return self

        def output(self, fields, **kwargs):
            return self

        def start(self):
            return {
                "message": "先看分布",
                "steps": [
                    {
                        "title": "分布统计",
                        "method": "describe",
                        "target_columns": ["value"],
                        "chart_type": "none",
                        "params": {},
                        "rationale": "先看分布形态",
                    }
                ],
                "options": [{"id": "go", "label": "按此执行", "action": "confirm"}],
            }

    df = pd.DataFrame({"group": ["A", "A", "B", "B"], "value": [1.0, 2.0, 3.0, 4.0]})
    profile = profile_dataframe(df)
    agent = DiscussionAgent(request_factory=RecordingRequest)
    agent.draft_plan(profile, "比较两组的 value 差异，缺失值怎么处理")

    info = captured["info"]
    assert "方法学要点" in info
    assert "连续变量·两组比较" in info
    assert "缺失数据" in info

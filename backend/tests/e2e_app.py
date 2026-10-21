"""Playwright E2E 用的桩模型后端（不依赖真实 LLM，不污染生产装配）。

启动：
    cd backend && python tests/e2e_app.py --port 8021
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile

# 允许以脚本方式运行（backend 加入 sys.path，找到 medsta 包）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


STUB_PLAN = {
    "message": "先描述 value 的分布，再比较 A/B 两组的差异。",
    "steps": [
        {
            "title": "分布统计",
            "method": "describe",
            "target_columns": ["value"],
            "chart_type": "histogram",
            "params": {},
            "rationale": "连续变量先看分布形态与离群值",
        },
        {
            "title": "组间比较",
            "method": "group_compare",
            "target_columns": ["value"],
            "chart_type": "boxplot",
            "params": {"group_column": "group"},
            "rationale": "两组连续变量，按正态性自动选择 t 或 Mann-Whitney",
        },
    ],
    "options": [
        {"id": "go", "label": "按此执行", "action": "confirm"},
        {"id": "explain", "label": "解释依据", "action": "explain"},
    ],
}


class _StubRequest:
    """ModelRequest 四段式替身：返回固定方案。"""

    def input(self, value):
        return self

    def info(self, value):
        return self

    def instruct(self, value):
        return self

    def output(self, fields, **kwargs):
        return self

    def start(self) -> dict:
        return STUB_PLAN


def build_app(data_root: pathlib.Path):
    from medsta.agents.discussion import DiscussionAgent
    from medsta.app import create_app

    app = create_app(data_root=data_root)
    app.state.service.set_agent(
        DiscussionAgent(request_factory=lambda: _StubRequest())
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="MedSta E2E stub backend")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--data-root", default="")
    args = parser.parse_args()

    root = (
        pathlib.Path(args.data_root)
        if args.data_root
        else pathlib.Path(tempfile.mkdtemp(prefix="medsta-e2e-"))
    )
    root.mkdir(parents=True, exist_ok=True)

    import uvicorn

    uvicorn.run(build_app(root), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

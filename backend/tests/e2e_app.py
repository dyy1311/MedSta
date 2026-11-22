"""Playwright E2E 用的桩模型后端（不依赖真实 LLM，不污染生产装配）。

启动：
    cd backend && python tests/e2e_app.py --port 8021
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
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
    # 桩后端不依赖真实 LLM：开发机存在真实 .env 时，后台解释任务
    # 会拿真实 InterpretationAgent 打真模型（烧 token），显式置 None
    app.state.service.set_interpret_agent(None)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="MedSta E2E stub backend")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--data-root", default="")
    args = parser.parse_args()

    # 未指定 --data-root 时用临时目录，并在启动时清掉上一轮残留：
    # Playwright 用 SIGTERM/SIGKILL 停 webServer，atexit 不保证执行，
    # 只靠退出清理会让 /tmp 累积 medsta-e2e-*（每轮一个会话目录）
    _temp_root: tempfile.TemporaryDirectory[str] | None = None
    if args.data_root:
        root = pathlib.Path(args.data_root)
    else:
        for stale in pathlib.Path(tempfile.gettempdir()).glob("medsta-e2e-*"):
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
        _temp_root = tempfile.TemporaryDirectory(prefix="medsta-e2e-")
        root = pathlib.Path(_temp_root.name)
    root.mkdir(parents=True, exist_ok=True)

    import uvicorn

    uvicorn.run(build_app(root), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

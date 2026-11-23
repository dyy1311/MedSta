"""039 B1：库代码不得使用 print（CLI 入口 launcher 除外）。"""
from __future__ import annotations

import pathlib
import re


def test_no_print_in_library_code() -> None:
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "medsta"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "launcher.py":
            continue  # CLI 工具面向用户输出豁免
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*print\(", text, re.M):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"库代码残留 print 调用：{offenders}（请改用 logging）"

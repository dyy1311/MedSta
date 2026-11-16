"""工作链模板存储（034）：`data_root/templates/<name>.json`，原子写。

模板是跨会话资产：{name, steps, created_at, updated_at}。
损坏文件跳过不报错；模板名宿主校验（防路径穿越）。
"""
from __future__ import annotations

import json
import os
import pathlib
import re

SNAPSHOT_VERSION = 1
_NAME_PATTERN = re.compile(r"^[\w\-\u4e00-\u9fa5]{1,64}$", re.UNICODE)

from medsta.stats.registry import get_tool


def is_safe_name(name: str) -> bool:
    """模板名安全校验：字母/数字/下划线/连字符/中文，禁路径分隔符与点。"""
    return bool(_NAME_PATTERN.match(name))


def validate_steps(steps: list) -> str | None:
    """校验模板步骤：非空且每个 method 已注册；返回错误信息或 None。"""
    if not isinstance(steps, list) or not steps:
        return "工作链为空，至少需要一个步骤"
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return f"步骤 {index + 1} 不是对象"
        method = str(step.get("method", ""))
        if get_tool(method) is None:
            return f"步骤 {index + 1} 引用了未知统计工具：{method}"
    return None


class TemplateStore:
    def __init__(self, root: str | pathlib.Path) -> None:
        self._root = pathlib.Path(root) / "templates"

    def _path_for(self, name: str) -> pathlib.Path:
        return self._root / f"{name}.json"

    def _serialize(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    def save(self, name: str, steps: list) -> dict:
        """保存模板（同名覆盖）；返回落盘后的模板载荷。"""
        import datetime

        existing: dict = {}
        path = self._path_for(name)
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                existing = {}
        now = datetime.datetime.now().isoformat(timespec="seconds")
        payload = {
            "version": SNAPSHOT_VERSION,
            "name": name,
            "steps": steps,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
        }
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(self._serialize(payload), encoding="utf-8")
        os.replace(tmp, path)
        return payload

    def load(self, name: str) -> dict | None:
        path = self._path_for(name)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None

    def delete(self, name: str) -> bool:
        path = self._path_for(name)
        if not path.is_file():
            return False
        path.unlink()
        return True

    def list_all(self) -> list[dict]:
        """全部合法模板，按 updated_at 倒序；损坏文件跳过。"""
        templates: list[dict] = []
        if not self._root.is_dir():
            return templates
        for path in sorted(self._root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(payload, dict) and payload.get("name"):
                templates.append(payload)
        templates.sort(key=lambda t: str(t.get("updated_at", "")), reverse=True)
        return templates

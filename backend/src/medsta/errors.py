"""统一错误码与 AppError：让失败可分类、可展示、可修复。

WS 错误契约：{"type":"error","code":...,"message":...,"hint":...,"detail":...}
"""
from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_REQUEST_FAILED = "MODEL_REQUEST_FAILED"
    DATA_REQUIRED = "DATA_REQUIRED"
    INVALID_PLAN = "INVALID_PLAN"
    MISSING_PARAM = "MISSING_PARAM"
    INVALID_PARAM = "INVALID_PARAM"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
    COLUMN_TYPE_MISMATCH = "COLUMN_TYPE_MISMATCH"
    ORDINAL_HINT = "ORDINAL_HINT"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    INTERRUPTED = "INTERRUPTED"
    NO_ACTIVE_RUN = "NO_ACTIVE_RUN"
    PROTOCOL_UNSUPPORTED = "PROTOCOL_UNSUPPORTED"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        hint: str = "",
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.detail = detail

    def to_event(self) -> dict:
        return {
            "type": "error",
            "code": self.code.value,
            "message": self.message,
            "hint": self.hint,
            "detail": self.detail,
        }


class ToolValidationError(ValueError):
    """计划校验失败（保留 ValueError 语义，兼容既有调用方）。"""

    def __init__(self, issues: list) -> None:
        self.issues = issues
        summary = "；".join(f"[{i.code}] {i.message}" for i in issues[:3])
        super().__init__(summary or "计划校验失败")

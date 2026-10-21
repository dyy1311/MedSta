"""共享测试夹具：数据根隔离、会话清场、标准样本与假模型契约。

原则：只隔离系统边界（文件系统、模型网络调用），不替换内部协作者。
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from medsta.app import create_app
from medsta.session.manager import manager


@pytest.fixture(autouse=True)
def _clean_session_registry():
    """SessionManager 是模块级单例：每个用例前后清空，避免跨用例串味。"""
    manager.clear()
    yield
    manager.clear()


@pytest.fixture
def data_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """独立数据根：上传文件、artifact、记录都落在 tmp_path。"""
    root = tmp_path / "sessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def app(data_root: pathlib.Path):
    return create_app(data_root=data_root)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def session_id(client: TestClient) -> str:
    return client.post("/sessions").json()["session_id"]


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """标准样本：三组连续值 + 二分类结局 + 有序序列。

    数值刻意构造为确定性（无随机），保证断言可重复。
    """
    return pd.DataFrame(
        {
            "group": ["A", "A", "A", "A", "B", "B", "B", "B", "C", "C", "C", "C"],
            "value": [10.0, 11.0, 12.0, 13.0, 20.0, 21.0, 22.0, 23.0, 30.0, 31.0, 32.0, 33.0],
            "outcome": [0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0],
            "age": [25, 31, 42, 38, 51, 47, 29, 60, 33, 45, 52, 27],
            "visit": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        }
    )


class RecordingFakeRequest:
    """模拟模型传输边界：记录四段式输入，返回预置结构化输出。"""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.input_value = None
        self.info_value = None
        self.instruct_value = None
        self.output_fields = None

    def input(self, value):
        self.input_value = value
        return self

    def info(self, value):
        self.info_value = value
        return self

    def instruct(self, value):
        self.instruct_value = value
        return self

    def output(self, fields, **kwargs):
        self.output_fields = fields
        return self

    def start(self) -> dict:
        return self.payload

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


@pytest.fixture(autouse=True)
def _default_data_root_in_tmp(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """无参 `create_app()` 也落 tmp：测试不得写真实 `backend/data`。

    9 处用例直接 `create_app()`（capabilities / spa_hosting / session_api /
    typing / survival_edges），走默认 `data/sessions`（cwd=backend）——
    每轮全量会在真实数据根留下若干 discussing 会话目录，dev 侧看起来像
    「刷新后多出陌生会话」。显式传 `data_root=` 的用例不受影响。
    """
    monkeypatch.setenv("MEDSTA_DATA_ROOT", str(tmp_path / "default-sessions"))


@pytest.fixture(autouse=True)
def _no_real_gateway(request, monkeypatch):
    """测试环境隔离真实模型网关（审查 P1 地雷）。

    项目根存在真实 `.env` 时 `_build_service` 会构建真实
    InterpretationAgent/ColumnTypeAdvisor——交付态 chat / AI 类型建议
    会打真模型并无限等待（test_export_chart_formats 曾因此挂死）。
    强制 app 工厂内 build_gateway 抛错，「测试不得依赖 .env」由约定
    变为机制；真实模型冒烟（real_llm marker，MEDSTA_REAL_LLM=1 才
    运行）显式豁免。
    """
    if request.node.get_closest_marker("real_llm"):
        return

    def _raise(*args, **kwargs):
        raise RuntimeError("测试环境不构建真实模型网关（conftest 隔离 .env）")

    # _build_service 内是函数局部 `from medsta.config import build_gateway`，
    # 调用期从 medsta.config 命名空间解析——补丁源头模块即可拦截
    monkeypatch.setattr("medsta.config.build_gateway", _raise)


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

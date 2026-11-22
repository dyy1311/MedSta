"""P1 地雷守护（审查发现）：测试环境不得构建真实模型网关。

开发机项目根存在真实 `.env` 时，`_build_service` 会构建真实
InterpretationAgent/ColumnTypeAdvisor——交付态 chat / AI 类型建议测试会打
真模型并无限等待（`test_export_chart_formats` 曾因此挂死）。conftest 的
autouse 夹具强制 app 工厂内 `build_gateway` 抛错（real_llm 冒烟豁免），
把「测试不得依赖 `.env`」从约定变为机制；本文件守护该机制不被回归。
"""
from __future__ import annotations

import pathlib


def test_app_factory_never_builds_real_agents(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """B1: 即使环境提供完整 LLM 配置（模拟开发机 .env），测试内 create_app
    也不得构建真实智能体（讨论 / 解释 / 类型建议全为 None）。"""
    from medsta.app import create_app

    for key, value in {
        "LLM_BASE_URL": "http://test.invalid/v1",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model",
    }.items():
        monkeypatch.setenv(key, value)

    app = create_app(data_root=tmp_path / "sessions")
    service = app.state.service

    assert service._agent is None
    assert service._interpret_agent is None
    assert service.type_advisor is None


def test_module_app_is_lazy(monkeypatch) -> None:
    """B2: 模块级 app 惰性构建——导入 medsta.app 不触发 create_app 副作用
    （真实数据根的 restore_all / 目录创建 / 网关构建）；首次访问才构建并缓存。"""
    import medsta.app as app_module

    assert "app" not in vars(app_module), "导入即构建了 app（应惰性）"

    sentinel = object()
    monkeypatch.setattr(app_module, "create_app", lambda *a, **k: sentinel)
    try:
        assert app_module.app is sentinel
        # memoize：同一实例重复返回（uvicorn 的 medsta.app:app 目标语义）
        assert app_module.app is sentinel
        assert "app" in vars(app_module)
    finally:
        # 还原：清掉 memoize 的 sentinel，后续需要时再惰性重建
        app_module.__dict__.pop("app", None)


def test_default_create_app_writes_into_tmp(tmp_path: pathlib.Path) -> None:
    """B3: 无参 `create_app()` 也不写真实 `backend/data`（autouse 重定向 MEDSTA_DATA_ROOT）。

    此前 9 处用例直接无参构建 app，每轮全量都在真实数据根留下 discussing 会话
    目录（dev 侧表现为「刷新后多出陌生会话」）。
    """
    from fastapi.testclient import TestClient

    from medsta.app import create_app

    app = create_app()
    assert str(tmp_path) in str(app.state.data_root)

    client = TestClient(app)
    session_id = client.post("/sessions").json()["session_id"]
    # 真实数据根不得出现该会话（cwd=backend，默认根即 backend/data/sessions）
    assert not (pathlib.Path("data/sessions") / session_id).exists()
    # 会话注册在 manager 中，落盘后目录在 tmp 而不是真实根
    from medsta.session.manager import manager

    assert manager.get(session_id) is not None

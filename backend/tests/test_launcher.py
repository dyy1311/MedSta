"""008 一键启动器：参数解析 / 命令构造 / 前置检查 纯函数测试。"""
import pytest

from medsta.launcher import (
    build_dev_commands,
    build_prod_commands,
    ensure_frontend_ready,
    parse_args,
)


def test_parse_args_defaults() -> None:
    """B1: 默认 dev 模式、后端 8000、前端 5173"""
    args = parse_args([])
    assert args.prod is False
    assert args.port == 8000
    assert args.frontend_port == 5173


def test_parse_args_prod_and_port() -> None:
    """B2: --prod 与 --port 注入"""
    args = parse_args(["--prod", "--port", "9000"])
    assert args.prod is True
    assert args.port == 9000


def test_build_dev_commands() -> None:
    """B3: dev 模式命令（uvicorn + npm run dev，端口注入）"""
    backend, frontend = build_dev_commands(port=8000, frontend_port=5173)
    assert backend == ["uvicorn", "medsta.app:app", "--host", "0.0.0.0", "--port", "8000"]
    assert frontend == ["npm", "run", "dev", "--", "--port", "5173", "--host", "0.0.0.0"]


def test_build_prod_commands() -> None:
    """B4: prod 模式命令（先 build 再单端口 serve）"""
    build_cmd, serve_cmd = build_prod_commands(port=9000)
    assert build_cmd == ["npm", "run", "build"]
    assert serve_cmd == ["uvicorn", "medsta.app:app", "--host", "0.0.0.0", "--port", "9000"]


def test_ensure_frontend_ready(tmp_path) -> None:
    """B5: node_modules 缺失返回 False；存在返回 True"""
    missing = tmp_path / "frontend-empty"
    ok = tmp_path / "frontend-ok" / "node_modules"
    ok.mkdir(parents=True)
    assert ensure_frontend_ready(missing) is False
    assert ensure_frontend_ready(ok.parent) is True

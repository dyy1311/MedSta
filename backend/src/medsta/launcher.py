"""一键启动器：dev 双子进程编排 / prod 构建后单端口托管。

纯函数（parse_args/build_*_commands/ensure_frontend_ready）可被 pytest 测试；
进程编排 run_dev/run_prod 为薄封装，冒烟验证。
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = _PROJECT_ROOT / "frontend"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MedSta 一键启动器")
    parser.add_argument("--prod", action="store_true", help="构建前端并由后端单端口托管")
    parser.add_argument("--port", type=int, default=8000, help="后端端口（默认 8000）")
    parser.add_argument(
        "--frontend-port", type=int, default=5173, help="dev 模式前端端口（默认 5173）"
    )
    return parser.parse_args(argv)


def build_dev_commands(*, port: int, frontend_port: int) -> tuple[list[str], list[str]]:
    backend = ["uvicorn", "medsta.app:app", "--host", "0.0.0.0", "--port", str(port)]
    frontend = [
        "npm", "run", "dev", "--",
        "--port", str(frontend_port), "--host", "0.0.0.0",
    ]
    return backend, frontend


def build_prod_commands(*, port: int) -> tuple[list[str], list[str]]:
    build_cmd = ["npm", "run", "build"]
    serve_cmd = ["uvicorn", "medsta.app:app", "--host", "0.0.0.0", "--port", str(port)]
    return build_cmd, serve_cmd


def ensure_frontend_ready(frontend_dir: Path = FRONTEND_DIR) -> bool:
    """node_modules 缺失时提示安装并返回 False。"""
    if (frontend_dir / "node_modules").is_dir():
        return True
    print(f"[launcher] 未找到 {frontend_dir / 'node_modules'}，请先执行：")
    print(f"[launcher]   cd {frontend_dir} && npm install")
    return False


# ---- 进程编排 ----


async def _pump(stream: asyncio.StreamReader, prefix: str) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        sys.stdout.write(f"[{prefix}] {line.decode(errors='replace')}")
        sys.stdout.flush()


async def run_dev(*, port: int, frontend_port: int) -> int:
    """并发启动后端与前端；任一退出则终止整组，Ctrl+C 优雅关闭。"""
    backend_cmd, frontend_cmd = build_dev_commands(port=port, frontend_port=frontend_port)
    cwd_by_name = {
        "backend": _PROJECT_ROOT / "backend",
        "frontend": FRONTEND_DIR,
    }
    procs: list[tuple[str, asyncio.subprocess.Process]] = []
    pumps: list[asyncio.Task] = []
    for name, cmd in (("backend", backend_cmd), ("frontend", frontend_cmd)):
        # start_new_session：子进程独立进程组，终止时可杀掉 npm→vite 整棵进程树
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd_by_name[name]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        procs.append((name, proc))
        pumps.append(asyncio.create_task(_pump(proc.stdout, name)))
        print(f"[launcher] {name} 已启动 (pid={proc.pid})")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async def wait_any() -> None:
        await asyncio.wait(
            [asyncio.create_task(p.wait()) for _, p in procs],
            return_when=asyncio.FIRST_COMPLETED,
        )
        stop.set()

    any_exit = asyncio.create_task(wait_any())
    stop_task = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait({any_exit, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    if done.pop() is any_exit:
        print("[launcher] 某个子进程已退出，终止整组…")
    else:
        print("[launcher] 收到退出信号，正在关闭…")

    for _, proc in procs:
        if proc.returncode is None:
            _signal_group(proc, signal.SIGTERM)
    for _, proc in procs:
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _signal_group(proc, signal.SIGKILL)
            await proc.wait()
    # 清理：先摘除信号 handler，避免 loop 关闭期间回调触发 RuntimeError
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.remove_signal_handler(sig)
    any_exit.cancel()
    stop_task.cancel()
    for task in pumps:
        task.cancel()
    await asyncio.gather(any_exit, stop_task, *pumps, return_exceptions=True)
    print("[launcher] 已全部退出")
    return 0


def _signal_group(proc: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    """向子进程整组发信号（覆盖 npm→vite 等派生进程）。"""
    import os

    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except ProcessLookupError:
        pass


def run_prod(*, port: int) -> int:
    """构建前端后单进程启动（SPA 托管在 app 内按 dist 存在性自动启用）。"""
    build_cmd, serve_cmd = build_prod_commands(port=port)
    import subprocess

    print("[launcher] 构建前端…")
    result = subprocess.run(build_cmd, cwd=str(FRONTEND_DIR))
    if result.returncode != 0:
        print("[launcher] 前端构建失败，终止启动")
        return result.returncode
    print("[launcher] 构建完成，启动单端口服务…")
    return subprocess.run(serve_cmd, cwd=str(_PROJECT_ROOT / "backend")).returncode


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not ensure_frontend_ready():
        return 1
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("[launcher] 未找到 uvicorn，请先在 Sta 环境安装后端：cd backend && pip install -e .[dev]")
        return 1
    if args.prod:
        return run_prod(port=args.port)
    return asyncio.run(run_dev(port=args.port, frontend_port=args.frontend_port))


if __name__ == "__main__":
    raise SystemExit(main())

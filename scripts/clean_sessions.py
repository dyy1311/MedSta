"""清理残留会话：测试 / 手工操作后把会话目录与执行记录归零。

用法（项目根执行）：

    python scripts/clean_sessions.py                     # 自动：服务在线走 API，否则离线删目录
    python scripts/clean_sessions.py --online --port 8000
    python scripts/clean_sessions.py --offline           # 停服后直接删 data_root 下的会话目录
    python scripts/clean_sessions.py --offline --purge-records

为什么默认走 API：会话同时存在于内存（`SessionManager`）与磁盘（快照/事件流/产物）。
只删磁盘会让运行中的服务继续返回「幽灵会话」，之后删除又 404。

数据根按 `create_app` 的口径解析：`MEDSTA_DATA_ROOT` > `backend/data/sessions` > `data/sessions`。
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
_CANDIDATE_ROOTS = (ROOT / "backend" / "data" / "sessions", ROOT / "data" / "sessions")


def resolve_data_root() -> pathlib.Path | None:
    """返回实际存在的数据根（都不存在时返回 None）。"""
    import os

    explicit = os.environ.get("MEDSTA_DATA_ROOT")
    if explicit:
        path = pathlib.Path(explicit)
        return path if path.exists() else None
    for candidate in _CANDIDATE_ROOTS:
        if candidate.is_dir():
            return candidate
    return None


def _call(url: str, method: str = "GET", token: str | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method=method)
    if token:
        request.add_header("X-Auth-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _service_online(base: str) -> bool:
    try:
        status, _ = _call(f"{base}/health")
        return status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def clean_online(base: str, token: str | None) -> int:
    import json

    status, body = _call(f"{base}/sessions", token=token)
    if status == 401:
        print("服务要求登录：请用 --token 传入登录令牌（或 X-Auth-Token）", file=sys.stderr)
        return 1
    if status != 200:
        print(f"列会话失败：HTTP {status}", file=sys.stderr)
        return 1
    sessions = json.loads(body).get("sessions", [])
    deleted = 0
    for item in sessions:
        session_id = item.get("session_id")
        if not session_id:
            continue
        code, _ = _call(f"{base}/sessions/{session_id}", method="DELETE", token=token)
        if code in (200, 204):
            deleted += 1
        else:
            print(f"删除 {session_id} 失败：HTTP {code}", file=sys.stderr)
    print(f"已通过 API 删除 {deleted} 个会话（服务内存与磁盘同步）")
    return 0 if deleted == len(sessions) else 1


def clean_offline(data_root: pathlib.Path, purge_records: bool) -> int:
    removed = 0
    for entry in sorted(data_root.iterdir()):
        if not entry.is_dir():
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed += 1
    print(f"已删除 {removed} 个会话目录：{data_root}")
    records = data_root.parent / "records"
    if records.exists():
        if purge_records:
            shutil.rmtree(records, ignore_errors=True)
            print(f"已删除执行记录：{records}")
        else:
            print(
                f"执行记录仍在 {records}（SQLite 句柄可能被运行中的服务持有）："
                "停服后加 --purge-records 清理"
            )
    return 0


def purge_e2e_temp() -> int:
    """清理 E2E 桩后端留下的 /tmp/medsta-e2e-*（Playwright 用信号停服，退出清理不保证）。"""
    import tempfile

    removed = 0
    for stale in pathlib.Path(tempfile.gettempdir()).glob("medsta-e2e-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
            removed += 1
    if removed:
        print(f"已清理 {removed} 个 E2E 临时数据目录")
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清理残留会话（离线删目录 / 在线走 API）")
    parser.add_argument("--online", action="store_true", help="强制走 HTTP API（需服务在线）")
    parser.add_argument("--offline", action="store_true", help="强制直接删除会话目录")
    parser.add_argument("--port", type=int, default=8000, help="服务端口（默认 8000）")
    parser.add_argument("--base", default="", help="服务地址（默认 http://127.0.0.1:<port>）")
    parser.add_argument("--token", default="", help="登录令牌（多用户模式需要）")
    parser.add_argument(
        "--purge-records", action="store_true", help="离线模式下一并删除 records 目录（需停服）"
    )
    args = parser.parse_args(argv)

    base = args.base or f"http://127.0.0.1:{args.port}"
    token = args.token or None

    if args.online and args.offline:
        parser.error("--online 与 --offline 互斥")

    use_online = args.online or (not args.offline and _service_online(base))
    if use_online:
        if not _service_online(base):
            print(f"服务不可达：{base}（改用 --offline 直接删目录）", file=sys.stderr)
            return 1
        code = clean_online(base, token)
        purge_e2e_temp()
        return code

    data_root = resolve_data_root()
    purge_e2e_temp()
    if data_root is None:
        print("未找到会话目录（MEDSTA_DATA_ROOT / backend/data/sessions / data/sessions）")
        return 0
    return clean_offline(data_root, args.purge_records)


if __name__ == "__main__":
    raise SystemExit(main())

"""MedSta 一键启动入口。

用法（mamba Sta 环境下，项目根执行）：
    python main.py            # dev 模式：后端 8000 + 前端 Vite 5173
    python main.py --prod     # prod 模式：构建前端，8000 单端口托管全部
    python main.py --port 9000 [--frontend-port 5174]
"""
import sys
from pathlib import Path

# backend/src 加入导入路径，使 medsta.launcher 可导入
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend" / "src"))

from medsta.launcher import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

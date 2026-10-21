---
name: medsta-launcher
overview: 新增项目根 main.py 一键启动器：dev 模式同时拉起 uvicorn 后端与 Vite 前端（Ctrl+C 优雅退出），prod 模式构建前端后由 FastAPI 单端口托管 dist；app.py 增加 SPA 静态托管；按 spec+TDD 流程实施并更新启动文档。
todos:
  - id: spec-launcher
    content: 创建 spec/008-app-launcher.md（行为列表/验收标准/测试映射）并移入 implementing 目录
    status: completed
  - id: launcher-core
    content: 用 [skill:tdd] 实现 backend/src/medsta/launcher.py 纯函数：build_dev_commands/build_prod_commands/ensure_frontend_ready/parse_args，配套 tests/test_launcher.py
    status: completed
  - id: spa-hosting
    content: 用 [skill:tdd] 在 app.py 增加 prod SPA 托管（assets 挂载 + catch-all fallback 与 API 豁免清单），补 tests/test_spa_hosting.py
    status: completed
  - id: main-entry
    content: 编写项目根 main.py 薄入口，接通 launcher 编排（dev 双子进程日志透传/Ctrl+C 整组退出、prod 先构建后单端口启动）
    status: completed
  - id: smoke-verify
    content: 真实冒烟：dev 模式双端口可访问且 Ctrl+C 后端口释放；--prod 模式单端口页面与 API 正常；复跑全部 pytest
    status: completed
  - id: governance-update
    content: spec 008 迁入 done，更新 docs/timeline.md、README.md 与 CODEBUDDY.md 的启动命令（python main.py / --prod）
    status: completed
---

## 产品概述

为 MedSta 新增项目根 `main.py` 一键启动器：用户只需在 mamba `Sta` 环境下执行 `python main.py` 即可同时拉起后端（FastAPI/uvicorn）与前端（Vite dev server），Ctrl+C 一键退出全部子进程；`--prod` 模式自动构建前端并由后端单端口托管，无需 Node 进程。

## 核心功能

- **dev 模式（默认）**：并发启动 uvicorn（8000 端口）与 `npm run dev`（5173 端口），日志带前缀透传，任一进程退出则终止整组，Ctrl+C 优雅关闭
- **prod 模式（--prod）**：自动执行 `npm run build`，随后由 FastAPI 托管 `frontend/dist`（SPA fallback 到 index.html），单端口 8000 访问完整应用
- **前置检查**：`frontend/node_modules` 缺失时提示先执行 `npm install` 并终止；uvicorn 包缺失时给出安装提示
- **可测试性**：参数解析、命令构造为纯函数，纳入 pytest；进程编排以真实冒烟验证

## 验收标准

- `python main.py` 后 8000/5173 均可访问，Ctrl+C 后两进程全部退出、端口释放
- `python main.py --prod` 构建后仅 8000 单端口提供页面与全部 API
- 既有 37 项 pytest 保持全绿，新增 main 模块单测通过

## 技术方案

- **技术栈**：Python 3.12（mamba Sta 环境）+ subprocess/asyncio 进程编排 + FastAPI StaticFiles；前端沿用 Vite 5
- **实现要点**：
- `main.py` 为薄入口：解析 `--prod/--port` 参数，调用 `medsta.launcher` 中的编排函数（launcher.py 置于 `backend/src/medsta/`，使纯函数可被 pytest 导入测试）
- dev 编排：`asyncio.create_subprocess_exec` 启动 uvicorn（`medsta.app:app`）与 `npm run dev`，stdout/stderr 逐行加 `[backend]`/`[frontend]` 前缀透传；监听 SIGINT/SIGTERM，任一子进程先退出则 `terminate()` 其余并等待回收
- prod 编排：先同步执行 `npm run build`（失败则退出并透传日志），再单进程启动 uvicorn；`app.py` 增加可选挂载——`dist/assets` 静态目录 + catch-all GET 路由 fallback 到 `index.html`（仅当请求路径不以 `/health`、`/sessions`、`/data`、`/ws`、`/docs`、`/openapi.json` 开头且 dist 存在时生效，避免拦截 API）
- 前端 prod 基准：Vite 默认 base `/`，无需改动 vite.config；`import.meta.env.DEV` 下无额外处理
- **测试**：按 [skill:tdd] 红绿循环覆盖纯函数（默认命令构造、prod 命令构造、端口参数传递、node_modules 缺失检测、SPA fallback 路由豁免清单）；进程编排用冒烟（启动→curl 双端口→SIGINT→断言端口释放）
- **spec 流程**：建立 `spec/008-app-launcher.md` 走 implementing → done，时间线记录

## Agent Extensions

### Skill

- **tdd**
- Purpose：对 launcher 的参数解析、命令构造、SPA fallback 豁免清单等纯函数按 RED-GREEN 垂直切片实现
- Expected outcome：新增行为均有先行测试且全绿，不破坏既有 37 项测试
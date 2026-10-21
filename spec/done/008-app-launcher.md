# 008 - 一键启动器 main.py（dev 双进程 / prod 单端口 SPA）

> 状态：done
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

当前需要两个终端分别启动后端（uvicorn 8000）与前端（Vite 5173）。目标：项目根 `python main.py` 一键拉起整个应用；`--prod` 构建前端后由 FastAPI 单端口托管。

## 范围

- 做：dev 双子进程编排（日志前缀透传、任一退出终止整组、Ctrl+C 优雅关闭）；prod 自动构建 + SPA 静态托管（assets 挂载 + catch-all fallback，API 路由豁免）；前置检查（node_modules / uvicorn 可导入）；参数解析 `--prod / --port / --frontend-port`
- 不做：多 worker、进程守护重启、Windows 兼容（Linux 为主）、前端代码改动

## 行为列表（TDD 循环队列）

- [x] B1: `parse_args([])` 默认 dev 模式、后端端口 8000、前端端口 5173
- [x] B2: `parse_args(["--prod", "--port", "9000"])` 得到 prod 模式与端口 9000
- [x] B3: `build_dev_commands` 返回 (backend_cmd, frontend_cmd)：uvicorn medsta.app:app 与 npm run dev，端口参数正确注入
- [x] B4: `build_prod_commands` 返回 build_cmd 与 serve_cmd（单端口）
- [x] B5: node_modules 缺失时 `ensure_frontend_ready` 返回 False 并给出安装提示；存在时返回 True
- [x] B6: SPA 托管：dist 存在时 GET / 返回 index.html、GET /assets/* 返回静态资源
- [x] B7: SPA catch-all 豁免 /health /sessions /data /ws /docs /openapi.json，不拦截 API
- [x] B8: dist 不存在时不注册 SPA 路由（dev 模式行为不变）

## 验收标准

- [硬门] B1–B8 pytest 全绿；既有 37 项测试不回归
- [硬门] 真实冒烟：dev 双端口可访问、SIGINT 后端口释放；--prod 单端口页面与 API 正常
- [软标] 日志前缀 [backend]/[frontend] 清晰可辨

## 契约与测试映射

| 行为 | 公共接口 | 测试 / 用例 |
|---|---|---|
| B1/B2 | `launcher.parse_args` | `tests/test_launcher.py` |
| B3/B4 | `launcher.build_dev_commands` / `build_prod_commands` | `tests/test_launcher.py` |
| B5 | `launcher.ensure_frontend_ready` | `tests/test_launcher.py` |
| B6/B7/B8 | `app.create_app`（dist 挂载开关） | `tests/test_spa_hosting.py` |

## 依赖与影响

- 修改 `app.py`（新增可选 SPA 挂载，函数签名不变）；新增 `launcher.py` 与根 `main.py`（薄入口）。不影响既有 API 契约。

## 备注

- Agently set_settings 语义教训不涉及；本 spec 全部为宿主确定性代码。

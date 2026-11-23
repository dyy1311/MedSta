# 038 - 可选单令牌鉴权

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：审查遗留 A2（零鉴权 + CORS * + 0.0.0.0）

## 背景与目标

当前所有路由零鉴权、CORS 全开、绑定 0.0.0.0——单机内部使用可接受，
但一旦局域网/公网部署即裸奔。本 spec 引入**可选单令牌鉴权**：
env `MEDSTA_AUTH_TOKEN` 未设置/空时行为与现状完全一致（现有测试零改动）；
设置后全路由（除 /health）要求令牌。

## 范围

- 做：
  - HTTP 中间件：`X-Auth-Token` 或 `Authorization: Bearer <token>` 校验；豁免 `/health`；401 统一响应
  - WS 升级校验：query `?token=`；错误时 accept 后 close(code=4401)（Starlette 在 accept 前拒绝需 403 握手，选 close code 方案保持 TestClient 兼容）
  - CORS 按 env 条件配置：鉴权开启时不再 `allow_origins=["*"]`
  - token 读取进 `app.state.auth_token`（一次性，启动时确定）
  - README 快速开始 + launcher 提示补充
- 不做（YAGNI）：多用户/会话级鉴权、登录页、HTTPS 终结（部署层职责）、令牌轮换

## 行为列表（TDD 循环队列）

- [x] B1: 未配置 MEDSTA_AUTH_TOKEN 时：全部现有行为不变（全量测试零改动即证明）
- [x] B2: 配置后无/错令牌的 HTTP 请求 → 401；正确令牌放行（含 /templates /export /data）
- [x] B3: /health 豁免（探活可用）
- [x] B4: WS 无 token → 收到 close(4401)；正确 token 正常收发
- [x] B5: SPA fallback 与静态 /data 同样受保护

## 验收标准

- [硬门] B1–B5 确定性测试；现有测试全绿（B1 的直接证据）
- [软标] 401 响应体含 hint（说明所需头格式）

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B1 | 全量回归 | 既有 450 用例零改动 |
| B2 | REST 全路由 | `tests/test_auth.py::test_missing_token_401` / `test_correct_token_passes` |
| B3 | /health | `tests/test_auth.py::test_health_exempt` |
| B4 | WS | `tests/test_auth.py::test_ws_token` |
| B5 | SPA/静态 | `tests/test_auth.py::test_spa_protected` |

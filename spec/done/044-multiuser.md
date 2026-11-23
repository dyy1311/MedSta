# 044 - 多用户化（课题组会话隔离）

> 状态：done
> 创建：2026-11-18 ｜ 敲定：2026-11-18 ｜ 完成：2026-11-18
> 上游：用户确认课题组共享部署；038 单令牌鉴权（全局共享、所有人可见所有会话）
> 附带修复：后端重启后恢复的会话前端不可见（缺会话列表接口）

## 背景与目标

课题组多人共用一套服务时，需要**每人只见自己的会话**。本 spec 引入用户体系：
登录换取令牌 → 令牌标识用户 → 会话归属用户并隔离。同时在 038 单令牌模式上
保持完全向后兼容（未配置用户时行为不变）。

## 范围

- 做：
  - 凭据：env `MEDSTA_USERS`（格式 `alice:pw1,bob:pw2`）；`POST /auth/login`
    {username,password} → `{token,username}`（secrets.token_urlsafe，内存表，重启失效需重登）
  - 兼容矩阵：`MEDSTA_USERS` 未配置 → 现状不变（038 单令牌或匿名，owner="local"）；
    配置后 → 登录模式（038 的 MEDSTA_AUTH_TOKEN 仍可作为附加后门？不：USERS 优先，单令牌失效）
  - 会话归属：Session.owner（创建时定、随快照持久化、恢复保留）；中间件统一校验
    （/sessions/{sid}**、/export/{sid}**、/report/{sid} 路径提取 sid → 非 owner 一律 404，不泄露存在性）；
    WS 连接校验 owner（token→username ≠ owner → close 4403）
  - `GET /sessions`：当前用户的会话列表（含重启恢复的）——补「重启后前端不可见」缺口
  - 模板保持全局共享（课题组共用分析套路合理）
  - 前端：401 时显示登录卡（用户名/密码）→ token 存 localStorage → 请求带
    `Authorization: Bearer`、WS 带 `?token=` → 启动加载会话列表
- 不做：注册/改密/角色权限、token TTL/刷新、用户级数据目录隔离（快照仍同目录，靠 owner 字段隔离）

## 行为列表（TDD 循环队列）

- [x] B1: 未配置 MEDSTA_USERS：现有测试零改动全绿（匿名 owner="local"，038 令牌模式不受影响）
- [x] B2: POST /auth/login 正确凭据 → token+username；错误凭据 401；未配置用户时 /auth/login 返回 404
- [x] B3: 登录后创建的会话 owner=username；他人（另一 token）访问该会话（上传/导出/报告/WS）一律 404/4403
- [x] B4: owner 随快照持久化，后端重启后归属保留
- [x] B5: GET /sessions 返回当前用户会话列表（含恢复会话），他人会话不可见
- [x] B6: 前端登录卡（401 触发）→ 登录 → 请求与 WS 带凭据 → 会话列表加载
- [x] B7: 未登录（无 token）访问受保护路由 → 401（沿用 038 中间件语义）

## 验收标准

- [硬门] B1–B7 确定性测试通过；既有测试零改动全绿（B1 兼容硬证据）；三道门不回退
- [软标] 登录失败提示不区分「用户不存在/密码错误」

## 测试映射

| 行为 | 测试 |
|---|---|
| B1 | 既有全量回归（零改动） |
| B2–B5 | `tests/test_multiuser.py` |
| B6 | `src/App.auth.test.tsx` |

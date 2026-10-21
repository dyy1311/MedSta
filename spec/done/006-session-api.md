# 006 - 会话编排 API：上传 / 讨论 / 确认 / 审阅 端到端

> 状态：done
> 完成日期：2026-10-17
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

把 002–005 的能力接线为端到端链路：上传数据（REST）→ 讨论生成方案（WS）→ 确认 → 执行 → 审阅请求（WS）→ 交付或修正回讨论。宿主会话状态机（session/manager.py）在流转点被调用；会话消息记录写入 RecordStore。

## 范围

- 做：`POST /sessions/{id}/data`（multipart 上传 CSV/xlsx，解析+缓存画像，返回摘要）；`SessionService.handle(session_id, event, send)` 消息编排（chat / confirm_plan / review）；`WS /ws/{session_id}` 薄封装。会话消息（用户消息、plan、交付）写入 RecordStore（collection=sessions）。
- 不做：鉴权、多会话并发隔离优化、历史回放接口（后续 spec）。上传文件存储用会话目录（backend/data/sessions/{id}/）；完整 TaskWorkspace 接线另行 spec。

## 消息契约（WS JSON）

- 客户端→服务端：`{"type":"chat","content":str}`；`{"type":"confirm_plan"}`；`{"type":"review","decision":"accept"}`；`{"type":"review","decision":"revise","content":str}`
- 服务端→客户端：`{"type":"data_profile","profile":{...}}`；`{"type":"plan","message":str,"steps":[...]}`；`{"type":"review_request","report":{...}}`；`{"type":"delivered","report":{...}}`；`{"type":"error","message":str}`

## 行为列表（TDD 循环队列）

- [x] B1: 上传 CSV 后返回 200 与画像摘要（row_count/column_count）
- [x] B2: discussing 态发 chat 得到 plan 事件（模拟模型），message 与 steps 来自 AnalysisPlan
- [x] B3: confirm_plan 后收到 review_request（含 report）
- [x] B4: review accept 后收到 delivered，会话状态为 delivered
- [x] B5: review revise（带修正意见）后会话回到 discussing，再次 chat 生成的新 plan 的 instruct 含修正意见
- [x] B6: chat 与交付事件写入 RecordStore，可按 session_id 查询

## 验收标准

- [硬门] B1–B6 测试 GREEN：B1 用 TestClient REST；B2–B5 用 SessionService 公共接口（模拟模型）；B6 用 LocalRecordStore
- [硬门] 端到端不发起真实模型请求

## 契约与测试映射

| 行为 | 公共接口 | 测试 / 用例 |
|---|---|---|
| B1 | `POST /sessions/{id}/data` | `tests/test_session_api.py::test_upload_data_returns_profile` |
| B2 | `SessionService.handle` | `tests/test_session_api.py::test_chat_yields_plan` |
| B3 | `SessionService.handle` | `tests/test_session_api.py::test_confirm_starts_execution` |
| B4 | `SessionService.handle` | `tests/test_session_api.py::test_accept_delivers` |
| B5 | `SessionService.handle` | `tests/test_session_api.py::test_revise_returns_to_discussion` |
| B6 | RecordStore | `tests/test_session_api.py::test_session_records_persisted` |

## 依赖与影响

- 依赖 002/003/005。前端 SPA（007）直接消费这些 REST/WS 契约。

## 备注

- WS 薄封装不单测（逻辑在 Service）；启动应用做一次冒烟即可。

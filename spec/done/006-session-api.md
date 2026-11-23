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
- 022 增量（向后兼容）：
  - `{"type":"interpretation","summary":str,"steps":[{"step_index":int,"finding":str,"caveat":str}],"caveats":[str],"unverified_numbers":[str]}`——`review_request` 之后异步推送；失败/关闭时不推，前端不显示解读区。
  - `{"type":"answer","answer":str,"caveats":[str],"unverified_numbers":[str]}`——`delivered` 态 `chat` 的答疑回复；该态下 `chat` 不再产 `plan`。
  - `delivered` 态 `review {"decision":"revise"}` 语义：回到讨论态并推 `back_to_discussion`，不返回 `NO_ACTIVE_RUN`。
- 029 增量（向后兼容）：
  - `plan` 事件新增可选字段 `estimand`（`EstimandSpec | null`：`population`/`variable`/`treatment`/`intercurrent_events[{event, strategy}]`/`summary_measure`）与 `sap_status`（`estimand_declared` 或 `exploratory`，由宿主计算）。缺省时前端按 `null`/`exploratory` 处理。
- 028 增量（向后兼容）：
  - `{"type":"dataset_added","dataset_id":str,"name":str,"profile":TableProfile,"imputed":bool,"source_dataset_id":str|null}`——`review_request` 之后推送，表示 `impute` 步骤产出了新的插补数据集。前端只追加工作区标签页，**不切换** `active_dataset_id`；用户手动切换后才改变分析对象。

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

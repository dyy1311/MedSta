# 010 - 实时交互：错误可见 / 流式输出 / 中断与继续

> 状态：done
> 创建：2026-10-18 ｜ 敲定：2026-10-18 ｜ 完成：2026-10-18

## 背景与目标

用户反馈"请求失败错误不可见（模型挂了？脚本报错？缺工具？）"，且生成/执行过程无反馈、无法中断。本 spec 建立错误码体系、模型增量流式输出、可中断的后台任务与继续能力。

## 范围

- 做：`errors.py`（12 个错误码 + AppError.to_event）；`ModelGateway.request_structured_stream`（单次请求内 SSE 增量 + 结构化结果，异常分类为 MODEL_REQUEST_FAILED）；`DiscussionAgent.draft_plan_stream`；`SessionService` 任务化（`_tasks`/`wait_idle`）、`interrupt`/`resume` 事件、`executing` 步骤进度；executor `on_step` 回调与单步失败隔离
- 不做：断线重连、跨进程任务恢复

## 行为列表（全部 GREEN）

- [x] B1: chat 流式下发 `stream` delta，随后 `plan` 事件含 options
- [x] B2: 模型失败 → `error{code: MODEL_REQUEST_FAILED, hint}`
- [x] B3: 生成中 `interrupt` → `interrupted{stage: thinking}` 并回到 discussing
- [x] B4: 确认执行 → `progress{stage: executing, step/total/title}` 与 `review_request`
- [x] B5: `resume` → `resumed`（有暂停审阅则重发 review_request）
- [x] B6: 未上传数据/未配置模型/方案非法 → 对应错误码事件

## 契约

WS 事件：`stream{channel,delta}`、`progress{stage,step,total,title}`、`interrupted{stage,message}`、`resumed{stage}`、`error{code,message,hint,detail}`；保留 chat/confirm_plan/review 旧协议。

## 测试映射

`tests/test_realtime.py`（5 项）+ `tests/test_session_api.py` 回归 + 真实模型流式冒烟（流式 7296 字符、中断成功）。

## 依赖与影响

依赖 009 的工具校验（INVALID_PLAN 携带 issues）；为 011 提供事件通道。前端 `App.tsx` 状态机消费这些事件。

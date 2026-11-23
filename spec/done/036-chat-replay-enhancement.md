# 036 - 会话消息流完整回放（035 增强）

> 状态：done
> 创建：2026-11-16 ｜ 敲定：2026-11-16 ｜ 完成：2026-11-16
> 上游：035 断线重连（其「不做」项：入站用户消息回放；events.jsonl 轮转）

## 背景与目标

035 落地后重连可补发服务端出站帧，但**用户自己发的消息**（chat 文本、确认/审阅动作）
不在事件流中——刷新页面或后端重启后，聊天区只能重建助手侧内容，用户气泡丢失，
对话上下文断裂。本 spec 把用户动作也记入事件流，实现会话历史的完整重建；
同时为 events.jsonl 增加简单轮转，防止单会话日志无限增长。

## 范围

- 做：
  - 用户动作帧落盘：`chat/confirm_plan/review/option/chart_choice/type_confirm/run_chain/plot_later/interrupt`
    在 `service.handle` 入口统一记录为 `{type:"<event>_user", ...精简字段}`（占 seq，写入 events.jsonl，不实时广播）
  - 回放：缺口补发自然包含用户帧；前端识别 `*_user` 帧渲染用户气泡
  - 幂等：回放帧经 ws 裸发（不经过 commit），不写回事件流
  - 轮转：events.jsonl 超过阈值时保留尾部 N 行重写（seq 单调性由计数器内存值保证）
- 不做（YAGNI）：
  - 服务端对用户消息的语义回应回放（由既有出站帧覆盖）
  - 多端会话隔离（同会话多连接仍各自回放）
  - 压缩加密

## 行为列表（TDD 循环队列）

- [x] B1: 用户 chat 后 events.jsonl 追加 `{type:"chat_user", content}` 帧（占 seq，出站帧 seq 续接）
- [x] B2: resume 回放包含 `chat_user` 帧；回放帧不写回事件流（幂等：回放后文件不增长）
- [x] B3: 轮转：超过阈值的 events.jsonl 被重写为尾部 N 行，seq 仍单调（计数器内存值不回退）
- [x] B4: 前端收到 `chat_user` 帧渲染用户消息气泡；`chat_user` 帧带 `seq` 并更新补发水位

## 验收标准

- [硬门] B1–B4 确定性测试通过；既有测试全绿
- [硬门] 用户帧内容精简（不含 review 报告等大 payload；review_user 只记 decision/content）
- [软标] 轮转阈值常量化（默认 2MB / 保留 2000 行）

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | WS chat + events.jsonl | `tests/test_reconnect.py::test_user_action_recorded` |
| B2 | resume+last_seq | `tests/test_reconnect.py::test_replay_includes_user_frames_idempotent` |
| B3 | EventLog 轮转 | `tests/test_reconnect.py::test_event_log_rotation` |
| B4 | 前端 handleEvent | `src/App.replay.test.tsx` 新增用例 |

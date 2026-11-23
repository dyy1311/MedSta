# 035 - WS 断线重连 + 历史回放

> 状态：done
> 创建：2026-11-16 ｜ 敲定：2026-11-16 ｜ 完成：2026-11-16
> 上游：032 会话持久化（快照）+ 033 工作链；解决审查 H2（断线后前端静默卡死）

## 背景与目标

WebSocket 断线后前端消息静默丢弃、界面永久卡死（busy 无提示）；
后端重启后会话虽可恢复（032）但事件流丢失。本 spec 让：
1. 出站事件带单调 `seq` 并落盘 `events.jsonl`（每会话一文件，追加写）
2. 客户端断线自动重连（指数退避）+ 连接状态指示
3. 重连携带 `last_seq`，服务端仅补发缺口帧（不重复投递）；后端重启后同样可回放

## 范围

- 做：出站帧 seq 注入与落盘（ws 层单点包装）；`resume` 扩展 `last_seq` 缺口回放；
  前端自动重连 + 状态徽标（已连接/重连中）；`seq` 随事件透传给前端记录
- 不做（YAGNI）：
  - 入站用户消息的持久化回放（聊天记录完整回放归后续；重连后用户此前发出的消息文本不在回放内）
  - events.jsonl 轮转/压缩（量小；备注后续评估）
  - 多端同步（同会话多连接各自回放，不互斥）

## 行为列表（TDD 循环队列）

- [x] B1: WS 出站事件带单调递增 `seq`，并追加落盘 `data_root/<sid>/events.jsonl`
- [x] B2: `resume` 携带 `last_seq` 时仅补发 seq 大于该值的缺口帧（原帧原 seq，不重复）
- [x] B3: 后端重启后（同一 data_root 重建应用）resume 仍可回放历史帧，seq 续接不回退
- [x] B4: 不带 `last_seq` 的 `resume` 行为不变（还原审阅/交付态）
- [x] B5: 前端断线自动重连（指数退避 1s→2s→…上限 10s），重连成功发送 `resume`+`last_seq`
- [x] B6: 连接状态变化回调（connected/reconnecting）驱动头部状态徽标

## 验收标准

- [硬门] B1–B6 确定性测试通过；既有测试全绿（含 426 后端 / 67 前端）
- [硬门] 落盘失败不阻塞投递（降级仅丢日志）；损坏行跳过
- [软标] events.jsonl 每会话单文件，格式一行一帧

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | WS 帧结构 + events.jsonl | `tests/test_reconnect.py::test_events_have_monotonic_seq_and_persist` |
| B2 | `resume`+`last_seq` | `tests/test_reconnect.py::test_resume_replays_gap_only` |
| B3 | 二次 `create_app` + resume | `tests/test_reconnect.py::test_replay_after_backend_restart` |
| B4 | `resume`（无 last_seq） | `tests/test_reconnect.py::test_resume_without_last_seq_unchanged` |
| B5/B6 | `connectSession` 重连 | `src/api/client.test.ts` 新增用例 |

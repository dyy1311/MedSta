# 005 - TriggerFlow 分析工作流编排与执行记录持久化

> 状态：implementing（B1–B4 已全绿）
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

"确认→执行→交付→修正回讨论"是应用层可见的多阶段编排：pipeline 执行后必须等待用户审阅（外部输入），确认则交付；修正则携带新方案回到执行（图可见回边）。编排用 Agently TriggerFlow（原生 owner）；执行/会话记录用 LocalRecordStore（原生 owner）持久化。

## 拓扑（图可见）

```
execute（跑 pipeline，产出 report）
  -> review（pause_for 等待用户审阅，payload 含 report）
  -> route（accept: delivered=True + 写执行记录；revise: emit("RE_EXECUTE", 新plan) 回到 execute）
flow.when("RE_EXECUTE").to(execute)  # 显式回边
```

## ModelRequest / 契约

无模型参与（执行态纯宿主计算）。记录契约：collection=`executions`，kind=`execution_report`，scope 含 `session_id`，content 为 ExecutionReport JSON。

## 行为列表（TDD 循环队列）

- [x] B1: run() 启动后进入审阅等待，interrupt payload 中含执行报告（report）
- [x] B2: 审阅 accept 后执行正常关闭，最终状态 delivered=True，report 为本次 plan 的执行结果
- [x] B3: 审阅 revise 携带新 plan 时重新执行新 plan 并再次等待审阅；再次 accept 后最终 report 为新 plan 结果
- [x] B4: 每次执行完成后，RecordStore 中可按 session_id 查到执行记录（含 report 内容）

## 验收标准

- [硬门] B1–B4 pytest-asyncio 走公共接口（AnalysisWorkflow.run + execution 句柄）GREEN
- [硬门] 回边在 flow 定义中图可见（RE_EXECUTE 事件），非 while True
- [软标] WebSocket 接线在 006 处理；本 spec 不涉及网络

## 契约与测试映射

公共接口：`medsta.pipeline.workflow.AnalysisWorkflow`——`async run(session_id, plan, df, artifact_dir)` 返回 execution 句柄；`async review(execution, decision)` 封装 continue_with。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `run` / `pending_interview` | `tests/test_workflow.py::test_run_pauses_for_review_with_report` |
| B2 | `review(accept)` | `tests/test_workflow.py::test_accept_delivers` |
| B3 | `review(revise)` | `tests/test_workflow.py::test_revise_reexecutes_new_plan` |
| B4 | RecordStore 查询 | `tests/test_workflow.py::test_execution_record_persisted` |

## 依赖与影响

- 依赖 004（PipelineExecutor/ExecutionReport）。被 006 WebSocket 会话编排消费。

## 备注

- resume 经 `execution.async_continue_with(interrupt_id, value)`；chunk 内 `async_pause_for(payload=..., resume_to="next")`。

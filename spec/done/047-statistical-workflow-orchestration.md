# 047 统计工作流编排：流程图方案 → 逐节点交付 → 断点续接

- 状态：done（2026-11-20 落地）
- 来源：用户实测反馈「一次性让模型构造复杂统计管线并填对所有参数过于困难和不稳定」

## 问题

当前 `chat → plan（一次性 steps） → confirm → 整条执行 → review`：

1. 方案的「管线结构」只以步骤列表呈现，用户看不出节点依赖与阶段；
2. 任一节点校验失败 → 整条链被拒（`INVALID_PLAN`），用户只能整条重来；
3. 执行中途失败 → 只有一份最终报告，未完成节点与失败原因混在一起；
4. 报错后用户补充信息，模型拿不到「已完成哪些节点、哪个节点失败、为什么」，只能重新出方案；
5. 模型缺少统计方法学知识（选择规则 / 报告规范），参数与结构都靠临场发挥。

## 目标流程

```
① 模型分析（tool-call 自检：列类型/组数/缺失）+ 工具目录 → 流程图方案（节点=现有工具）
        ↓ plan 事件（steps + flow：节点依赖 + mermaid 文本）
② 用户讨论 / 修改 → 确认工作流（confirm_plan）
        ↓
③ 逐节点执行：每个节点完成即 step_result（表格/图/错误），失败只影响该节点
        ↓ 失败节点可 retry_step（宿主重跑）或 amend_step（模型按补充信息重写该节点）
④ 全部节点完成 → review_request → delivered（保持既有审阅/导出链路）
```

## 行为列表（可测）

- **B1** `plan_flow(plan)` 由 `steps[].depends_on` 生成 `{nodes[], mermaid, order}`；缺省依赖降级为线性链，非法依赖（越界/自环/反向）忽略并降级。
- **B2** `plan` 事件携带 `flow`；旧客户端忽略该字段仍可用。
- **B3** 执行器每完成一个节点回调 `on_step_result(index, total, step_report)`（成功与失败都回调）。
- **B4** 每次回调下发 `step_result` 帧（含 index/title/status/table/artifact/error/result），前端可逐节点展示。
- **B5** 节点失败不阻断后续节点（已有隔离，补测试）；最终 `review_request` 仍包含失败节点与其 `error`。
- **B6** `retry_step {index, overrides}`：宿主用当前数据重跑该节点及其下游依赖，更新报告并广播 `step_result(updated=true)`；越界/未执行 → `INVALID_PARAM`。
- **B7** `amend_step {index, note}`：带「已确认图 + 该节点 + 错误 + 用户补充」调用模型重写该节点，宿主校验后重跑；模型不可用 → `MODEL_UNAVAILABLE`。
- **B8** `SessionContext` 按 `(owner, session_id)` 分层存取：记录数据摘要、已确认节点、节点状态/错误、用户补充；`snapshot()` 输出给模型的最小上下文（≤2000 字）。
- **B9** 上下文在 `delete_session` / `cleanup_duplicates` 后释放，不留内存残留。
- **B10** 内置统计 skills（SAMPL 报告规范 + 检验选择决策树 + 常见误用）按用户诉求关键词挑选并注入讨论 prompt；digest 长度受限。
- **B11** 前端：方案卡渲染流程图（节点/箭头，可展开看参数）；执行期逐节点状态（待执行/进行中/完成/失败）；失败节点提供「补充信息并重试」。

## 验收标准

| 类型 | 标准 |
|---|---|
| 硬门 | B1–B11 每条至少一个确定性测试；后端 ruff/mypy/pytest 全绿；前端 tsc/vitest 全绿；E2E 全流程不回归 |
| 软标 | 流程图节点名称与工具目录一致（宿主校验，不靠模型自觉）；节点级交付在真实浏览器可读 |

## 测试映射

| 行为 | 测试 |
|---|---|
| B1 | `tests/test_flow_graph.py` |
| B2 | `tests/test_flow_graph.py::test_plan_event_carries_flow` |
| B3/B5 | `tests/test_step_delivery.py::test_executor_reports_each_step` |
| B4 | `tests/test_step_delivery.py::test_step_result_frames_streamed` |
| B6 | `tests/test_step_delivery.py::test_retry_step_reruns_node` |
| B7 | `tests/test_step_delivery.py::test_amend_step_uses_context` |
| B8/B9 | `tests/test_session_context.py` |
| B10 | `tests/test_stats_skills.py` |
| B11 | `frontend/src/chat/PlanFlow.test.tsx`、`frontend/src/App.stepDelivery.test.tsx` |

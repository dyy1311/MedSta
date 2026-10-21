# 003 - ReAct 讨论智能体与 AnalysisPlan 契约

> 状态：done
> 完成日期：2026-10-17
> 创建：2026-10-17 ｜ 敲定：2026-10-17 ｜ 完成：2026-10-17

## 背景与目标

讨论态核心：根据数据画像与用户诉求，生成结构化 `AnalysisPlan`（分析步骤、方法、目标列、图表类型），并产出面向用户的讨论消息。方案可随用户修正意见迭代（重新生成 plan）。宿主负责契约校验；模型只做语义决策（选方法、定步骤）。

## 范围

- 做：`AnalysisPlan` / `PlanStep` pydantic 契约（约束枚举：方法族 describe/correlation/regression/timeseries_forecast/hypothesis_test；图表类型 histogram/boxplot/scatter/line/bar/heatmap/none）；`DiscussionAgent.draft_plan(profile, user_request, revision_note=None)` 公共接口：四段式 ModelRequest 调用 + 宿主校验 + 返回 plan 与讨论消息；修正意见注入（revision_note 非空时作为额外 instruct 约束）。
- 不做：多轮对话记忆管理（005 会话编排处理）、真实模型质量评估（软标，另行验证）、pipeline 执行（004）。

## ModelRequest 输出契约（四段式）

- input：用户分析诉求（+ 修正意见）
- info：数据画像 JSON 摘要（TableProfile）
- instruct：你是数据分析方案设计师；步骤需可被宿主 pipeline 执行；方法/图表只能取枚举值；目标列必须来自画像列名
- output（fields）：`message`(str, 给用户的说明)、`steps`(list[dict])，每个 step：`title`(str)、`method`(enum)、`target_columns`(list[str])、`chart_type`(enum)、`params`(dict, 可空)

## 行为列表（TDD 循环队列）

- [x] B1: 模拟模型返回合法 step 集合时，draft_plan 返回通过校验的 AnalysisPlan，message 与 steps 透传
- [x] B2: 画像注入：ModelRequest 的 info 内容包含 TableProfile 的序列化摘要（模拟请求记录捕获）
- [x] B3: 契约校验：模拟模型返回非法 method 枚举时抛出 pydantic ValidationError（宿主为校验权威）
- [x] B4: 修正注入：revision_note 非空时出现在请求 instruct 中
- [x] B5: 目标列约束：step 引用画像中不存在的列名时抛出 ValueError（实施修订：宿主校验用 ValueError 表达确定性约束，非 pydantic ValidationError）

## 验收标准

- [硬门] B1–B5 模拟模型（传输边界注入）测试 GREEN
- [硬门] 测试不发起真实网络请求
- [软标] 真实模型下方法/图表枚举命中率高（后续最小真实验证，不在本 spec 硬门内）

## 契约与测试映射

公共接口：`medsta.agents.discussion.DiscussionAgent.draft_plan`。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `draft_plan` | `tests/test_discussion.py::test_draft_plan_returns_validated_plan` |
| B2 | `draft_plan` | `tests/test_discussion.py::test_profile_injected_as_info` |
| B3 | `draft_plan` | `tests/test_discussion.py::test_invalid_method_rejected` |
| B4 | `draft_plan` | `tests/test_discussion.py::test_revision_note_in_instruct` |
| B5 | `draft_plan` | `tests/test_discussion.py::test_unknown_target_column_rejected` |

## 依赖与影响

- 依赖 001（ModelGateway）、002（TableProfile）。AnalysisPlan 契约被 004 pipeline 执行器消费。

## 备注

- 枚举用 pydantic Literal 校验；宿主额外校验 target_columns ⊆ 画像列名（模型决策的确定性约束由宿主把关）。

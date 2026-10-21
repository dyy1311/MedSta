# 020 - 正确性护栏：类型推断 / Logistic 分离 / 协议错误码

> 状态：done
> 创建：2026-10-21 ｜ 敲定：2026-10-21 ｜ 完成：2026-10-21
>
> 落地结果：B1–B8 全绿；后端 200 collected（199 passed + 1 真模型 skip）、前端 35 passed、
> E2E 2 passed；`npm run build` / `npm run lint` 通过。Logistic 准分离夹具已替换为正常数据，
> 分离场景独立断言；Firth 惩罚回归未实现，已在方法学文档与 TO_DO 标注。

## 背景与目标

spec 019 的评估报告将三项「结果看起来对、方法学上站不住」的风险列为 P0：

1. 整数型测量变量（年龄、血压等）被推断为 `ordinal`，参数检验被默认降级为非参数，损失功效；
2. Logistic 回归在完全/准完全分离时输出溢出或天文数字的 OR/CI（实测 `OR=5.9e65`、`converged=False`），
   用户无法从结果中识别「不可估计」；
3. 未知 WS 消息类型复用 `INVALID_PLAN`，把协议问题与方案问题混为一谈。

本 spec 在宿主确定性校验层加三道护栏，并补一个降低逐列修正成本的前端操作。

## 范围

- 做：整数测量变量的列名/范围识别；Logistic 分离与未收敛守卫；`PROTOCOL_UNSUPPORTED` 错误码；类型确认卡「数值列全部设为连续」。
- 不做：Firth 惩罚回归（仅文案与文档标注为后续选项）；改变 0/1 整数的既有类型语义；引入新依赖；模型提示词改造。

## 行为列表（TDD 循环队列）

- [x] B1: 整数列命中测量指标名称（`age`/`height`/`bmi`/`sbp`/`年龄`/`血压` 等，英文按词元匹配）→ `continuous`
- [x] B2: 非负且跨度 ≤10 的整数列（Likert 1–5、评分 0–10）→ `ordinal`；跨度 >10 的整数计数 → `continuous`
- [x] B3: 索引列、浮点列、布尔/日期/文本列判定保持不变；0/1 整数仍为 `ordinal`
- [x] B4: Logistic 完全/准完全分离（未收敛或 max|β|≥15 或 OR/CI 非有限）→ `ValueError`，消息含「分离」「OR 不可估计」与可操作建议，不返回 OR
- [x] B5: Logistic 正常数据仍返回 `odds_ratios`/`accuracy`/`auc`，所有 OR 与 CI 有限
- [x] B6: 未知 WS 消息类型 → `PROTOCOL_UNSUPPORTED`；缺方案确认仍为 `INVALID_PLAN`
- [x] B7: 前端错误卡对 `PROTOCOL_UNSUPPORTED` 显示「协议不支持」
- [x] B8: 类型确认卡「数值列全部设为连续」仅把 `continuous`/`ordinal` 列改为 `continuous`，`categorical`/`index` 不动，确认时整体下发

## 验收标准

- [硬门] B1–B8 均有对应确定性测试，且先确认 RED 再实现。
- [硬门] 后端 `pytest` 全绿；前端 `vitest`、`build`、`lint` 全绿；E2E 2 项仍通过。
- [硬门] Logistic 测试夹具不再包含准分离数据；分离场景独立断言报错。
- [硬门] `/capabilities` 与既有 WS 契约结构不变（仅新增错误码字符串）。
- [软标] 分离错误文案能让用户知道下一步做什么（减少协变量/合并稀疏类别/增大样本/Firth）。
- [软标] 「数值列全部设为连续」不误改类别列与索引列，按钮语义在 UI 上自解释。

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `profile_dataframe(df)` → `columns[name].type` | `test_profile_quality.py::test_integer_measurement_columns_are_continuous` |
| B2 | 同上 | `test_profile_quality.py::test_small_range_integers_stay_ordinal`、`test_wide_range_integer_counts_are_continuous` |
| B3 | 同上 | `test_profile_quality.py::test_inference_covers_four_slots`（回归） |
| B4 | `stats.methods.logistic_regression` | `test_stats_methods.py::test_logistic_rejects_perfect_separation` |
| B5 | 同上 | `test_stats_methods.py::test_logistic_normal_data_has_finite_odds_ratios`、`test_stats_registry.py::test_logistic_regression_outputs_odds_ratios` |
| B6 | `SessionService.handle` → WS `error.code` | `test_ws_contract.py::test_unknown_message_returns_protocol_unsupported` |
| B7 | `ErrorCard` 渲染 | `App.flow.test.tsx::错误事件…`（扩展协议码断言） |
| B8 | `TypeReviewCard` → `onConfirm(types)` | `App.flow.test.tsx::数值列全部设为连续` |

## 依赖与影响

- `data/profiler.py`：`_infer_column_type` 已接收 `name` 参数但未使用；本次仅增强整数分支，函数签名与 `ColumnType` 枚举不变。
- `stats/methods.py`：`logistic_regression` 输出结构不变；异常经 `execute_step` 的失败隔离转为 `EXECUTION_FAILED`。
- `errors.py`：新增枚举成员为纯增量；前端 `AppErrorPayload.code` 为 `string`，`types.ts` 无需改动。
- `frontend/src/chat/TypeReviewCard.tsx`：仅本地状态批量赋值，消息契约不变。
- 影响测试：`test_profile_quality.py`、`test_stats_methods.py`、`test_stats_registry.py`、`test_ws_contract.py`、`test_upload_contract.py`（如断言 age 类型）、`App.flow.test.tsx`。
- 文档：`docs/statistics-methods.md`、`docs/design-notes.md`、`docs/timeline.md`、`TO_DO.md`、`CODEBUDDY.md`。

## 备注

- 英文列名必须按分隔符切词匹配：`age` 是 `stage`/`percentage` 的子串，简单 `in` 会误判；中文使用子串匹配。
- 0/1 整数保持 `ordinal` 是刻意取舍：改动会波及类型映射与非参数路径，收益低、回归面大。
- 分离检测阈值取 `max|β| ≥ 15`（OR≈3.3e6）+ 未收敛 + 非有限值；误报时按安全方向降级（拒绝输出而非给错数）。

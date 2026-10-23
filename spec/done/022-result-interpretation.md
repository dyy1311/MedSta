# 022 - 结果解释与交付后答疑分流

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

产品定位是「交付图表与解释建议」，但当前交付物只有表格、图表与策略链（`docs/evaluation-report.md` §4 P0-6）。
评估报告同时指出 G0/G3 缺口：无「探索性」标记与升级路径。

本 spec 补齐两件事：

1. **结果解释**：执行完成后由宿主把统计结果整理成证据包注入模型，模型只撰写受控自然语言解读，
   以「汇总 + 每步一句结论 + 全局提醒」补进既有审阅卡。
2. **交付后答疑分流**：当前 `_on_chat` 在 `delivered` 态会无条件重新出方案（`service.py:182-185`），
   用户看完解释想追问时会被迫重规划；本 spec 让交付态默认走答疑，显式操作才回到方案调整。

## 范围

- 做：证据白名单抽取、受控解读契约、因果断言硬门、未核验数值软标、句数截断、`MEDSTA_INTERPRET` 开关与句数上限、解释非阻塞推送、交付态答疑、交付态 revise 回讨论、前端内嵌渲染。
- 不做：Estimand/SAP 五要素、结果导出（解释不进 CSV/XLSX）、多轮解释追问上下文记忆、解释的重新生成按钮、真模型质量自动评估、`print` → `logging` 重构。

## 职责与数据流契约

### Owner 不变量

| 不变量 | 拥有者 | 说明 |
|---|---|---|
| 证据包里有哪些数值 | 宿主（`interpretation.py::build_evidence`） | 按 method 白名单抽取，模型不能扩大范围 |
| 解读文字 | 模型 | 只做句子组织，不做统计推断 |
| 因果断言判定 | 宿主（安全守卫） | 类比 schema 校验，不是语义路由 |
| 句数上限与截断 | 宿主 | 确定性、可测 |
| 未核验数值标记 | 宿主 | `unverified_numbers` 不由模型输出 |
| 解释是否展示 | 宿主（开关 + 校验结果） | 失败静默降级 |
| 交付态路由（答疑 / 改方案） | 宿主（`SessionManager.status`） | 前端不决定服务端路由 |

### 节点账本

| 节点 | 类型 | 边界理由 |
|---|---|---|
| 证据组装 | 宿主阶段 | 需要执行报告，且必须在模型调用前确定可见数值 |
| `interpret` | ModelRequest | 需要语义组织；一次调用产出完整解释 |
| 校验与截断 | 宿主阶段 | schema/因果/越界/句数都是确定性规则 |
| `answer` | ModelRequest | 答疑是独立问题，输入输出契约不同，不与 interpret 合并 |

不合并的理由：`interpret` 在报告生成后自动触发、输出结构化多段；`answer` 由用户问题驱动、输出单段文本。
合并会引入「无问题的自动答疑」或「有问题的批量解释」，两者都违反字段消费原则。

### 值/事件边

| 边 | 生产者 | 校验 | 消费者 |
|---|---|---|---|
| `profile + report + plan → evidence` | `service._start_interpretation` | 白名单键存在性 | `interpret` 的 info |
| `raw model output → Interpretation` | `ModelGateway` | pydantic → 因果门 → 越界 → 截断 → 未核验数值 | WS `interpretation` |
| `interpretation → 前端 review 消息` | `App.tsx` | `lastIndexOf("review")` 定位 | `ReviewCard` |
| `answer → 前端消息流` | `App.tsx` | 类型收窄 | `ChatPanel` |
| `review {decision:revise} → 回讨论` | `service._on_review` | `status == DELIVERED && execution is None` | `back_to_discussion` |

### 生产必要性

解释产出 3 个字段（`summary`/`steps`/`caveats`）全部有渲染位置；`unverified_numbers` 为宿主字段，不进 `_OUTPUT_FIELDS`。
不请求思维链、不请求置信度分数、不请求重排建议——无消费方。

## 行为列表（TDD 循环队列）

- [x] B1: 证据包只含画像摘要、各方法白名单结论数值、步骤 rationale 与失败码，不含数据行与整份 `result`
- [x] B2: 解读出现因果断言（如「治疗组导致结局改善」）→ 硬门拒绝并重试一次；仍违规则整体不展示
- [x] B3: 否定语境（「不能说明存在因果关系」）不触发因果硬门
- [x] B4: 每步默认 1 句；超上限按中文句号边界截断；`max_sentences` 越界 clamp 到 1–5
- [x] B5: `step_index` 越界的条目被丢弃，其余保留；全部越界则整体不展示
- [x] B6: 未核验数值：`0.0287` 接受 `0.029`/`0.03`；`p<0.001` 形式放行；凭空数字进入 `unverified_numbers`
- [x] B7: 解释生成不修改 `report.steps` 任一字段（深拷贝快照比对）
- [x] B8: 模型异常或 schema 不合规 → 返回 `None`，不抛异常、不推 error 事件
- [x] B9: `MEDSTA_INTERPRET=0` 时执行完成不启动解释任务、不推 `interpretation`
- [x] B10: 默认开启时 `review_request` 之后推送 `interpretation`，payload 含 summary/steps/caveats/unverified_numbers
- [x] B11: 解释返回时步骤签名与当前报告不一致（新执行已覆盖）→ 丢弃不推送
- [x] B12: 交付态 chat 走答疑：推 `answer`、不产 plan、状态仍为 `delivered`
- [x] B13: 交付态 `review {decision:"revise"}` 回讨论并推 `back_to_discussion`，不返回 `NO_ACTIVE_RUN`
- [x] B14: 审阅卡渲染每步 finding、未核验角标、全局 caveats，交付态提供「调整分析方案」入口
- [x] B15: `interpretation` 事件按最后一条 review patch，不污染历史卡片；`answer` 消息独立渲染

## 验收标准

- [硬门] B1–B15 均有确定性测试；先确认 RED 再最小实现
- [硬门] `ExecutionReport.steps` 结构不变，仅新增可选 `interpretation` 字段（旧前端可忽略）
- [硬门] 解释失败/超时/丢弃时，`review_request` 与 accept 交付链路完全不受影响
- [硬门] 后端 `pytest` 全绿且覆盖率不低于 83%；前端 `npm test` / `build` / `lint` 全绿；E2E 2 项不回归
- [硬门] `MEDSTA_INTERPRET=0` 与句数上限边界（0/1/5/99）行为确定
- [软标] 解读读起来像研究者写的结论，而非模板拼接；不夸大、不替代统计判断
- [软标] `caveat` 能指导下一步（补样本 / 换方法 / 谨慎解读）
- [软标] 因果守卫不误伤正确的否定表述与「相关不等于因果」类说明

## 契约与测试映射

### interpret 四段式

| 段 | 内容 |
|---|---|
| input | 用户原始分析诉求（`session` 最近一次 chat；缺失时退化为 `plan.message`） |
| info | 画像摘要（行数/列数/类型）+ 逐步证据（ref/title/method/rationale/params/target_columns/values/warning/error） |
| instruct | 只引用 info 中出现的数值；禁止因果断言；每步最多 N 句；仅简体中文；证据不足时明说「当前结果无法判断」 |
| output | `summary: str`、`steps: [{step_index: int, finding: str, caveat: str}]`、`caveats: [str]` |

字段契约：

| 字段 | 类型 | 可空 | 约束 | 消费方 |
|---|---|---|---|---|
| `summary` | str | 否 | ≤120 字，不含因果断言 | 审阅卡顶部 |
| `steps[].step_index` | int | 否 | ∈ `[0, len(report.steps))`，越界丢弃 | 定位步骤 |
| `steps[].finding` | str | 否 | ≤`max_sentences` 句，按 `[。！？]` 截断 | 步骤标题下 |
| `steps[].caveat` | str | 是 | ≤60 字 | 步骤提示 |
| `caveats` | list[str] | 是 | 0–4 条；宿主强制追加探索性声明 | 卡片底部提醒条 |

### answer 四段式

| 段 | 内容 |
|---|---|
| input | 用户问题 |
| info | 与 interpret 相同的证据包 |
| instruct | 只基于已交付结果回答；不得新增分析或编造数值；超出证据范围答「当前交付中无法回答」；禁止因果断言 |
| output | `answer: str`、`caveats: [str]` |

### 证据白名单

| method | 抽取键 |
|---|---|
| `describe` | `stats.<col>.overall.{n,mean,median,q25,q75,min,max}`、`distinct` |
| `missing_report` | `row_count`、`complete_rows`、`columns.<col>.{missing,rate}` |
| `normality_test` | `columns.<col>.{statistic,p_value,normal}` |
| `levene_test` | `statistic`、`p_value`、`homogeneous` |
| `group_compare` | `test`、`statistic`、`p_value`、`mean_diff`、`ci95`、`cohens_d`、`strategy.final_method`、`groups` |
| `anova` | `test`、`statistic`、`p_value`、`eta_squared`/`epsilon_squared`、`strategy.final_method`、`groups` |
| `chi_square` | `chi2`、`dof`、`p_value`、`cramers_v`、`odds_ratio`、`strategy.final_method` |
| `correlation` | `method`、`pairs`（按 |r| 取前 3）、`table.stats` |
| `regression` | `n`、`r_squared`、`adj_r_squared`、`f_pvalue`、`coefficients`（前 5 项的系数名/估计/p） |
| `logistic_regression` | `n`、`pseudo_r_squared`、`odds_ratios`（前 5）、`accuracy`、`auc`、`event_rate` |
| `timeseries_forecast` | `slope`、`intercept`、`r_squared`、`forecast_n`、`forecast_values`（首尾各 1） |
| `aggregate_table` | `group_column`、`agg`、`table.rows`（前 10 行） |

每步通用：`title`、`method`、`status`、`error.code`、`error.message`（失败步骤也要能解释原因）。

### 行为 → 测试

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `build_evidence(report, plan, profile)` | `tests/test_interpretation.py::test_evidence_uses_whitelist_only` |
| B2 | `InterpretationAgent.interpret` | `test_interpretation.py::test_causal_claim_rejected_after_retry` |
| B3 | 同上 | `test_interpretation.py::test_negated_causality_is_allowed` |
| B4 | `_truncate_sentences` / `InterpretConfig` | `test_interpretation.py::test_sentence_cap_and_clamp` |
| B5 | `InterpretationAgent.interpret` | `test_interpretation.py::test_out_of_range_step_index_dropped` |
| B6 | `_unverified_numbers` | `test_interpretation.py::test_rounding_and_inequality_not_flagged` |
| B7 | `interpret` + `ExecutionReport` 快照 | `test_interpretation.py::test_report_steps_untouched` |
| B8 | `interpret` 异常路径 | `test_interpretation.py::test_model_failure_returns_none` |
| B9 | `SessionService` + `InterpretConfig(enabled=False)` | `test_qa_flow.py::test_disabled_interpret_emits_no_frame` |
| B10 | WS `interpretation` | `test_qa_flow.py::test_review_then_interpretation_frame` |
| B11 | `_interpret` 签名比对 | `test_qa_flow.py::test_stale_interpretation_dropped` |
| B12 | WS `answer` | `test_qa_flow.py::test_delivered_chat_answers_without_plan` |
| B13 | WS `review` revise | `test_qa_flow.py::test_delivered_revise_returns_to_discussion` |
| B14 | `ReviewCard` 渲染 | `ReviewCard.interpretation.test.tsx` |
| B15 | `App.tsx` 事件 patch | `App.interpretation.test.tsx` |

## 依赖与影响

- `agents/interpretation.py`（新增）：`InterpretationAgent`（`interpret`/`answer`）、`build_evidence`、`_causal_violation`、`_truncate_sentences`、`_unverified_numbers`、`EXPLORATORY_CAVEAT`。
- `config.py`：新增 `InterpretConfig`（`enabled`/`max_sentences`，`from_env`）。
- `session/service.py`：`__init__` 接收 `interpret_agent`/`interpret_config`；`_generate_plan` 记录最近诉求；`_execute_plan` 后启动解释任务；`_on_chat` delivered 分流；`_on_review` delivered-revise 扩展；`_on_interrupt` 取消解释任务。
- `app.py`：装配 agent 与 config；模型未配置时解释静默关闭。
- `frontend/src/types.ts`：`StepInterpretation`/`Interpretation`/`ExecutionReport.interpretation?`/`WsEvent` 加 `interpretation`、`answer`；`ChatMessage` 加 `answer`。
- 契约同步：`spec/done/006-session-api.md` 补两个事件与交付态 revise 语义。
- 文档：`docs/design-notes.md`（因果守卫定位、答疑归属状态机、白名单原则）、`docs/timeline.md`、`TO_DO.md`、`.env.example`。

## 备注

- **不引入 `report_id`**：前端复用 `delivered` 已验证的「最后一条 review」定位；后端用步骤签名 `[(method, title), ...]` 防串台。
- **因果守卫是合规守卫**，不是「用正则做语义判断」：先匹配「因素/干预/治疗/用药/分组/暴露/变量/指标 + 0–12 字 + 导致/引起/造成/使得/决定/证明/致使」，再检查匹配点前 12 字内是否有「不能/无法/不足以/并不/未/不应/不可」予以豁免。
- **未核验数值要防误报**：对每个证据数值生成 `round(e, k) for k in 0..3` 的允许集，并对 `p<0.001` 形式单独放行；否则角标会失去意义。
- **同步阻塞**：`ModelGateway.request_structured` 是同步的，解释与答疑必须 `asyncio.to_thread`，否则阻塞事件循环。
- **开关通过显式构造注入**，测试不依赖 `.env`。

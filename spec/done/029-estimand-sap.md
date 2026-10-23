# 029 - Estimand / SAP 结构化（ICH E9(R1) 五要素）

> 状态：done
> 创建：2026-10-23 ｜ 敲定：2026-10-23 ｜ 完成：2026-10-23

## 背景与目标

方案卡目前只说明「用什么方法」，没说明「这个分析在回答什么问题」。
本 spec 按 ICH E9(R1) 为方案补上估计目标（Estimand）五要素，并把「探索性 vs 已声明估计目标」的
状态判定收回宿主。

**教材 0 覆盖**：`Estimand / 估计目标 / SAP / 统计分析计划 / 伴发事件 / intercurrent` 在
《医学统计学》第 8 版中全部为 0 次，只有 1 处泛提「试验方案」。全部依据 **ICH E9(R1) Addendum (2019)**，
文案必须标注来源。

## 范围

- 做：`EstimandSpec` 契约（五要素）、宿主判定 `sap_status`、模型可选生成、方案卡折叠展示、
  caveat 按状态分流、证据包注入。
- 不做：SAP 摘要导出、事前注册、盲态与样本量论证、五要素文本与数据列的语义校验、
  前端编辑五要素（走现有「补充」通道）。

## 关键设计决策

1. **`EstimandSpec` 全字段默认空值**：模型可能只填一部分，pydantic 不能因此拒绝整份方案。
   完整性由宿主判定：四个文本要素全非空 → `estimand_declared`，否则 `exploratory`。
   `intercurrent_events` 允许为空（表示无伴发事件），不参与完整性判定——把「无伴发事件」判成
   「未声明」会让大量真实场景被误标。
2. **`sap_status` 是计算值，不是存储字段**：不作为 `AnalysisPlan` 字段，避免模型或前端伪造；
   由 `sap_status_of(plan)` 纯函数计算，在 `plan` 事件组装时显式写入。
3. **措辞红线**：即使五要素齐全也只说「已声明估计目标」，不出现 `pre-specified` 或
   用于描述本项目流程的「确证性」。用测试扫描文案锁住。
4. **caveat 二选一，不叠加**：已声明用 `ESTIMAND_DECLARED_CAVEAT`，未声明用现有
   `EXPLORATORY_CAVEAT`；两条并列会互相稀释。
5. **不新增 WS 事件**：estimand 随 `plan` 事件下发，修改走现有 supplement/revise。

## 行为列表（TDD 队列，16 条）

- [x] B1: 四文本要素齐全 → `sap_status=estimand_declared`
- [x] B2: 缺任一文本要素 → `exploratory`
- [x] B3: `estimand is None` → `exploratory`
- [x] B4: `intercurrent_events` 为空列表不影响状态判定
- [x] B5: 非法 `strategy` 值被 pydantic 拒绝
- [x] B6: 模型输出含 estimand 时进入 plan（非流式）
- [x] B7: 流式路径同样保留 estimand
- [x] B8: 模型不输出 estimand 时方案正常生成，不报错、不阻断
- [x] B9: `plan` 事件含 `estimand` 与 `sap_status`
- [x] B10: `build_evidence` 含 estimand 与 sap_status
- [x] B11: caveat 按 `sap_status` 二选一，且不叠加
- [x] B12: 后端文案不出现 `pre-specified` 与描述本系统流程的「确证性」
- [x] B13: 前端 PlanCard 折叠展示五要素与状态徽章
- [x] B14: 探索性时默认展开并列出缺失项
- [x] B15: `estimand` 为 null 时渲染提示而非空白，旧 plan 事件不报错
- [x] B16: `/capabilities` 的 planned 含 `sap_export`

## 验收标准

- [硬门] B1–B16 均有确定性测试，先确认 RED 再最小实现
- [硬门] `sap_status` 只由宿主计算，前端不推导、模型不可写
- [硬门] caveat 分流互斥（同一次解读只出现一条）
- [硬门] 文案扫描测试通过（无 `pre-specified`、无「确证性分析」式表述）
- [硬门] 后端全绿且覆盖率 ≥83%；前端 vitest/build/lint 全绿；E2E 2 项不回归
- [软标] 「探索性」提示能让用户明白缺的是哪一要素

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 |
|---|---|---|
| B1–B5 | `discussion.sap_status_of` | `test_estimand.py` |
| B6–B9 | `DiscussionAgent.draft_plan` / `draft_plan_stream`、`service` plan 事件 | `test_estimand.py` / `test_plan_guard.py` |
| B10/B11 | `agents.interpretation.build_evidence` / `_sanitize` | `test_interpretation.py` |
| B12 | 文案常量扫描 | `test_estimand.py::test_no_confirmatory_wording` |
| B13–B15 | `PlanCard` | `PlanCard.estimand.test.tsx` |
| B16 | `GET /capabilities` | `test_capabilities.py` |

## 关键字段

```python
class IntercurrentEvent(BaseModel):
    event: str = ""
    strategy: Literal[
        "treatment-policy", "hypothetical", "composite",
        "while-on-treatment", "principal-stratum",
    ] = "treatment-policy"

class EstimandSpec(BaseModel):
    population: str = ""
    variable: str = ""
    treatment: str = ""
    intercurrent_events: list[IntercurrentEvent] = Field(default_factory=list)
    summary_measure: str = ""

SAP_STATUS_DECLARED = "estimand_declared"
SAP_STATUS_EXPLORATORY = "exploratory"
```

## 依赖与影响

- `agents/discussion.py`：新增契约与 `sap_status_of`；`_BASE_INSTRUCT` 增第 8 条（无法确定时留空、禁止编造）；
  `_OUTPUT_FIELDS` 增 `estimand`。
- `agents/interpretation.py`：新增 `ESTIMAND_DECLARED_CAVEAT`；`_sanitize` 按状态二选一；
  `build_evidence` 注入 estimand 与 sap_status。
- `session/service.py`：plan 事件增 `estimand` 与 `sap_status`。
- `api/routes_capabilities.py`：planned 增 `sap_export`。
- 前端：`types.ts`、`ChatPanel.tsx`、`PlanCard.tsx`。
- 文档：`statistics-methods.md`、`design-notes.md`、`timeline.md`、`TO_DO.md`、`CODEBUDDY.md`、`006-session-api.md`。

## 备注

- 两条生成路径（`draft_plan` / `draft_plan_stream`）都要测，流式漏测是隐蔽回归。
- `answer` 路径的 caveat 也要分流，避免同一份交付的解读与答疑口径不一致。
- 前端默认展开策略：探索性默认展开（提示缺失），已声明默认折叠。
- `estimand` 是可选字段，旧 plan 事件前端按 null 处理。

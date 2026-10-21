---
name: 020-correctness-guards
overview: 新增 spec 020 并实施三项正确性护栏：整数型连续变量识别（避免年龄等被误判 ordinal 而降级非参数）、Logistic 完全/准完全分离检测（阻止溢出 OR/CI 下发）、未知 WS 消息独立错误码 PROTOCOL_UNSUPPORTED；配套前端「数值列全部设为连续」与错误卡标签，按 TDD 补测试并同步文档。
todos:
  - id: write-spec-020
    content: 用 [skill:tdd] 编写 spec/implementing/020-correctness-guards.md（B1–B8 行为、硬门/软标、测试映射）并记 design-notes
    status: completed
  - id: integer-continuous
    content: 先 RED 补类型推断用例，再改 profiler 白名单与跨度规则，同步 age 相关断言
    status: completed
    dependencies:
      - write-spec-020
  - id: logistic-guard
    content: 先 RED 加分离/非有限用例，再实现 Logistic 守卫并替换准分离测试夹具
    status: completed
    dependencies:
      - write-spec-020
  - id: protocol-code
    content: 新增 PROTOCOL_UNSUPPORTED 错误码与错误卡标签，更新 WS 契约用例
    status: completed
    dependencies:
      - write-spec-020
  - id: type-review-bulk
    content: TypeReviewCard 增「数值列全部设为连续」并补 Vitest 交互用例
    status: completed
    dependencies:
      - integer-continuous
  - id: docs-and-regression
    content: 更新方法学与文档，跑后端 pytest、前端 test/build/lint、E2E，spec 迁 done
    status: completed
    dependencies:
      - logistic-guard
      - protocol-code
      - type-review-bulk
---

## 用户需求

在 spec 019 完成全链路测试与评估后，按评估报告的 P0 建议启动第一项改进：**正确性护栏（spec 020）**，约 1 天、零新依赖，防止「结果看起来对、方法学上站不住」。

## 产品概述

不新增页面，聚焦三类会误导结论的隐患，并补一处降低操作成本的交互：

- 整数型连续变量（年龄、身高、体重、血压等）不再被误判为「数值-等级型」而被动降级为非参数检验
- Logistic 回归在完全/准完全分离时不再输出溢出或天文数字的 OR/CI，而是给出可读、可操作的失败信息
- 未知 WebSocket 消息类型使用独立错误码，不再与「方案校验失败」混用
- 类型确认卡新增「数值列全部设为连续」一键操作

## 核心功能

- 类型推断：列名白名单（中英文测量指标）+ 取值范围规则区分测量值与评分/分级；索引列、浮点、布尔、日期、文本判定保持不变；0/1 整数仍为等级型
- Logistic 护栏：拟合后检测未收敛、系数绝对值过大、OR/CI 非有限值，命中即报错并提示减少协变量/合并稀疏类别/增大样本或改用 Firth
- 协议错误码：新增 `PROTOCOL_UNSUPPORTED`，错误卡显示「协议不支持」，`INVALID_PLAN` 仅用于方案问题
- 前端一键操作：仅把 continuous/ordinal 列统一设为 continuous，categorical/index 不动
- 回归保障：被替换的准分离测试夹具改为正常数据；全量后端、前端、E2E 测试保持绿灯

## 技术栈

沿用现有栈，不引入新依赖：Python 3.12 + pandas + statsmodels + pytest（`asyncio_mode=auto`）；React 18 + TypeScript + Vitest + Testing Library；Playwright 仅做既有 E2E 回归。

## 实施方案

### 策略：三个独立纵向切片，逐条 RED → GREEN

1. **类型推断切片**：`data/profiler.py` 已接收 `name` 参数但未使用，直接在其内部增加确定性判定，不改函数签名与 `ColumnType` 枚举。判定顺序保持「布尔/日期 → 索引 → 整数细分 → 浮点 → 文本」，仅在整数分支插入：

- 命中测量指标白名单 → `continuous`
- 否则全为非负且 `max-min ≤ 10` → `ordinal`（Likert/评分/分级，与现状一致）
- 否则宽范围整数计数 → `continuous`

2. **Logistic 切片**：`stats/methods.py` 的 `logistic_regression` 在 `fit` 后、`np.exp` 前增加守卫。命中即抛 `ValueError`（executor 会转为用户可见的 `EXECUTION_FAILED`，无需新错误码）。
3. **协议错误码切片**：`errors.py` 增加枚举成员（纯增量），`session/service.py` 仅在未知消息分支改用新码；前端 `ErrorCard` 增加标签，未知码仍有「请求失败」兜底。

### 关键决策与取舍

- **列名匹配必须做词元匹配，不能用简单子串**：`age` 是 `stage`、`percentage` 的子串，直接 `"age" in name` 会误判。英文按分隔符（`_ - 空格`）切词后比对；中文（年龄/身高/体重/血压等）用子串匹配，避免误伤。
- **0/1 整数继续判为 ordinal**：布尔型语义列在类型映射中走非参数/分类路径，改动会波及 `test_type_mapping`/`test_typing` 的既有契约，收益低、风险高。
- **分离检测阈值取 `|β| ≥ 15` + 未收敛 + 非有限值三重条件**：准分离通常表现为系数 10 以上、SE 爆炸；阈值过高会漏检，过低会误伤强关联变量。三重条件组合兼顾召回与误报，误报时的文案引导用户减少协变量，属安全降级。
- **不实现 Firth 惩罚回归**：零新依赖且会改变输出契约（profile likelihood CI），本轮只在错误文案与方法学文档中标注为后续选项。
- **性能**：类型推断为每列 O(1) 词元匹配；分离检测为 O(p) 有限性检查，不额外拟合，对现有执行耗时可忽略。
- **爆炸半径**：生产代码只改 6 个文件，契约均为增量（新增错误码、新增按钮），既有 `AnalysisPlan`/WS 事件/`ExecutionReport`/`types.ts` 结构不变。

### 实现要点

- 现有 `test_stats_registry.py` 的 Logistic 夹具已实测为准完全分离（`converged=False`、`OR(score)=5.9e65`），必须替换为与结局弱相关的正常数据并保留 OR/accuracy/AUC 结构断言；分离场景移入 `test_stats_methods.py` 单独断言报错。
- 类型推断改动会连带影响 `test_profile_quality.py`、`test_upload_contract.py`、`test_typing.py` 中的 age 断言，需同步更新为 continuous，并确认 `test_type_mapping` 未受影响。
- 前端按钮只改本地 `types` 状态，确认仍走 `onConfirm(types)` 整体下发，不新增消息类型。
- `docs/statistics-methods.md` 增补「整数值测量变量的识别规则」与「Logistic 分离时 OR 不可估计、不汇报」；`CODEBUDDY.md` 修正错误码数量描述并补 profiler 语义。

## 架构设计

改动集中在「宿主确定性校验」层，符合项目 Owner 划分：模型仍只做语义决策，类型判定与数值护栏由宿主代码完成。数据流不变：上传 → profiler 推断 → 类型确认（可一键修正）→ 计划校验 → 执行（Logistic 护栏在此拦截）→ 交付；错误统一经 `AppError.to_event()` 或 executor 失败隔离下发。

## 目录结构

```
/home/xdy/MedSta/
├── spec/implementing/020-correctness-guards.md   # [NEW] 行为列表 B1–B8、硬门/软标、测试映射；全绿后迁 spec/done/
├── backend/src/medsta/
│   ├── data/profiler.py                          # [MODIFY] 启用 name 参数：测量指标白名单（词元匹配）+ 非负且跨度≤10 判 ordinal + 宽范围整数判 continuous；索引/浮点/文本分支不变
│   ├── stats/methods.py                          # [MODIFY] logistic_regression 增加分离/未收敛/非有限值守卫，抛带操作建议的 ValueError；正常数据输出结构不变
│   ├── errors.py                                 # [MODIFY] 新增 PROTOCOL_UNSUPPORTED 枚举成员（增量，不影响既有码）
│   └── session/service.py                        # [MODIFY] 未知消息类型改用 PROTOCOL_UNSUPPORTED；其余 INVALID_PLAN 用法不变
├── backend/tests/
│   ├── test_profile_quality.py                   # [MODIFY] 年龄/中文年龄→continuous、0–5 分级→ordinal、宽范围计数→continuous、index 与浮点回归不变
│   ├── test_stats_methods.py                     # [MODIFY] 分离数据→ValueError 且含「分离」；正常数据 OR/CI 全部 isfinite
│   ├── test_stats_registry.py                    # [MODIFY] 替换准分离夹具为正常数据，保留 odds_ratios/accuracy 断言
│   ├── test_ws_contract.py                       # [MODIFY] 未知消息断言改为 PROTOCOL_UNSUPPORTED；缺方案确认仍为 INVALID_PLAN
│   ├── test_upload_contract.py                   # [MODIFY] 同步 age 列类型断言（如受影响）
│   └── test_typing.py                            # [MODIFY] 同步类型推断断言（如受影响）
├── frontend/src/
│   ├── chat/ErrorCard.tsx                        # [MODIFY] CODE_LABELS 增加 PROTOCOL_UNSUPPORTED: 协议不支持
│   ├── chat/TypeReviewCard.tsx                   # [MODIFY] 新增「数值列全部设为连续」按钮：仅 continuous/ordinal → continuous
│   └── App.flow.test.tsx                         # [MODIFY] 一键连续后 type_confirm 的 types 断言；错误卡渲染协议不支持标签
├── docs/statistics-methods.md                    # [MODIFY] 类型识别规则、Logistic 分离边界与 Firth 说明
├── docs/timeline.md                              # [MODIFY] 追加 2026-10-21 spec 020 记录
├── docs/design-notes.md                          # [MODIFY] 记录「列名词元匹配」「分离检测三重条件」决策
├── TO_DO.md                                      # [MODIFY] P0 勾选进度、更新已知限制
└── CODEBUDDY.md                                  # [MODIFY] 错误码数量、profiler 类型推断说明
```

## 关键结构

```python
# backend/src/medsta/data/profiler.py（接口不变，仅语义增强）
_CONTINUOUS_NAME_HINTS: tuple[str, ...]  # 英文按词元匹配，中文按子串匹配
def _infer_column_type(series: pandas.Series, name: str, position: int) -> ColumnType: ...
```

```python
# backend/src/medsta/stats/methods.py（守卫契约）
def logistic_regression(df, step, params) -> dict:
    """完全/准完全分离、未收敛或 OR/CI 非有限时抛 ValueError，消息含可操作建议。"""
```

## Agent Extensions

### Skill

- **tdd**
- Purpose: 按 RED→GREEN→REFACTOR 逐条推进 spec 020 的行为列表，确保每条护栏先有失败断言再改实现
- Expected outcome: 每个切片都有明确的 RED 记录，随后全量 pytest、vitest、E2E 转绿，spec 可迁入 done
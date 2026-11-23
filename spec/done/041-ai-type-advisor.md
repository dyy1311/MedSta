# 041 - 模型辅助列类型确认（AI 确认数值类型）

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：用户需求「设计一个工具，能让模型帮我确认数值类型」；多用户化顺延为 042

## 背景与目标

列类型目前由 profiler 规则推断 + 用户手动确认。规则推断无法处理**语义**：
「分期 1/2/3/4」是等级还是连续？「编号」是索引还是类别？模型可基于
列名语义 + 取值样本 + 统计特征给出**类型建议与理由**，用户一键采纳或忽略——
延续产品原则：模型只建议（语义决策），宿主校验，用户敲定。

## 范围

- 做：
  - `agents/type_advisor.py` ColumnTypeAdvisor：每列产出
    `{name, suggested_type, confidence, reason}`（结构化契约，宿主校验类型合法）
  - 证据组装（宿主白名单，不传全量数据）：列名/规则推断类型/样本值（前 5 个唯一值）/
    缺失数/类别基数/数值范围
  - WS `{"type":"suggest_column_types"}` → `{"type":"column_type_suggestions",
    "suggestions":[...]}`（含每列建议；非法建议类型由宿主丢弃并标注 skipped）
  - 前端 ProfileTable「AI 确认类型」按钮 + 建议徽标（建议类型+理由）+
    「采纳」（单列/全部采纳，复用现有单列与批量 PATCH）
- 不做（YAGNI）：自动改类型（不经用户确认）；离线模型；类型建议持久化

## 行为列表（TDD 循环队列）

- [x] B1: `suggest_column_types` → 模型收到每列证据契约（名称/推断类型/样本值/统计），
      前端收到 suggestions 事件（每列建议+理由）
- [x] B2: 模型给出的非法类型建议被宿主丢弃（不出现在 suggestions，不崩）
- [x] B3: 未上传数据 → DATA_REQUIRED 错误帧
- [x] B4: 模型不可用（未配置）→ MODEL_UNAVAILABLE 错误帧
- [x] B5: 前端建议徽标渲染（建议类型+理由）；单列「采纳」与「全部采纳」调用类型修改

## 验收标准

- [硬门] B1–B5 确定性测试（假模型注入）；既有测试全绿；三道门不回退
- [软标] reason 一句话；confidence 0–1

## 测试映射

| 行为 | 测试 |
|---|---|
| B1–B4 | `tests/test_type_advisor.py` |
| B5 | `src/workspace/ProfileTable.test.tsx` 追加 |

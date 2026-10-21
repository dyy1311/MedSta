# 016 - 类型驱动映射与前置类型确认

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

变量类型是统计方法选择的第一依据（对应门禁 G0"问题分层"）：连续型才能做参数检验；等级型优先非参数；类别型走频数/卡方；索引列排除。同时在讨论前增加"类型敲定"前置节点。

## 范围

- 做：ToolSpec.accepts 列类型声明；validate_step COLUMN_TYPE_MISMATCH / ordinal 降级提示 / index 拒绝；default_chart_for 类型→默认图并注入 chart_config；type_review/type_confirm 前置节点（未敲定时 chat 拦截，确认后自动继续 pending chat）；模型 info 注入列类型摘要
- 不做：自动类型再推断（用户确认后即为准）

## 行为列表（TDD 循环队列）

- [x] B1: group_compare/anova/normality 对 categorical 目标列返回 COLUMN_TYPE_MISMATCH（建议 chi_square/频数）
- [x] B2: ordinal 目标列用于参数检验时给 ORDINAL_HINT 降级提示（不阻断，自动走非参数）
- [x] B3: index 列参与统计返回 COLUMN_TYPE_MISMATCH（提示索引列默认排除）
- [x] B4: chi_square 对 continuous 列返回 COLUMN_TYPE_MISMATCH（建议分箱或改连续方法）
- [x] B5: default_chart_for：continuous→histogram，categorical→bar/pie，ordinal→bar
- [x] B6: 未敲定类型时 chat → type_review 事件（列类型表）且不调模型；type_confirm 后自动继续 pending chat 生成方案
- [x] B7: 模型 info 含列类型摘要（name:type 列表）

## 验收标准

- [硬门] B1–B7 pytest GREEN；真实模型冒烟：类型确认前不产生模型调用

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B1–B4 | `registry.validate_step` | `tests/test_type_mapping.py` |
| B5 | `plotting.default_chart_for` | `tests/test_type_mapping.py` |
| B6/B7 | `SessionService.handle` | `tests/test_type_gate.py` |

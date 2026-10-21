# 013 - 统计工具槽位化、检验策略链与显著性规范

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

统计方法选择必须显式可解释：工具以 `task`（sta_task）+ 槽位声明；检验自动走"正态性→方差齐性→不平衡提示→最优方法→次优降级"策略链并输出 `strategy`；卡方做期望频数/数据量分析；显著性统一 α 与星号标注；多重比较 Holm/Bonferroni 校正。

## 范围

- 做：ToolSpec 增加 `task/slots/applicability`；新工具 `levene_test`、`aggregate_table`；`pie` 图表；group_compare/anova 策略链；chi_square 期望频数策略链（2×2 自动 Fisher）；`significance_label`；anova ≥3 组 overall+pairwise+校正；所有检验结果含 alpha/significant/stars
- 不做：生存分析、MICE、Dunnett/gatekeeping

## 行为列表（TDD 循环队列）

- [x] B1: tool_catalog 每项含 task/applicability/slots；validate_step 对槽位缺失报 MISSING_PARAM
- [x] B2: levene_test 输出 statistic/p/homogeneous
- [x] B3: aggregate_table 按 group_col×value_col×agg 输出表格数据
- [x] B4: pie 图表渲染（分类计数）
- [x] B5: group_compare 策略链：正态数据+t 齐性→t；正态+不齐→Welch；非正态→Mann-Whitney；strategy.steps 记录每步判定与次优建议
- [x] B6: anova 同策略链（ANOVA/Welch?简化 ANOVA/Kruskal）+ ≥3 组 pairwise（Holm 校正后 p 与标注）+ 多重性提醒文案
- [x] B7: chi_square 策略链：期望频数分析；2×2 期望不足自动 Fisher 并说明；R×C 不足给建议；输出 strategy
- [x] B8: significance_label 星号与 significant 判定；检验结果统一含 alpha/significant/stars
- [x] B9: PlanStep.rationale 缺失 → MISSING_PARAM（宿主拒绝，见 011 需求）

## 验收标准

- [硬门] B1–B9 pytest GREEN，既有 74 项不回归
- [软标] strategy 文案可读、可直接展示

## 契约与测试映射

公共接口：`stats/registry.py`（catalog/validate/execute）、`stats/methods.py`（策略链）、`stats/significance.py`（significance_label/p_adjust）、`agents/discussion.py`（rationale 校验）。测试：`tests/test_slots_strategy.py`、`tests/test_discussion.py` 增补。

## 依赖与影响

registry 结构变更影响 methods/plotting；PlanStep 增 `step_id`（可选）与 `rationale`（必填）。

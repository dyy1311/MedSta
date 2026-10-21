# 015 - 变量类型槽位与画像编辑

> 状态：done
> 创建：2026-10-19 ｜ 敲定：2026-10-19 ｜ 完成：2026-10-19

## 背景与目标

用户需要按医学统计习惯为每列标注变量类型：连续型（整数值）/ 等级型（数值等级）/ 类别型 / 序列索引（默认排除统计）。类型由系统推断建议、用户在画像表中下拉修正，并作为后续方法与图表映射的依据。

## 范围

- 做：四类类型（continuous/ordinal/categorical/index，保留 datetime/boolean 兼容）；profiler 推断建议；TableProfile.type_confirmed；`PATCH .../columns` 修改类型（宿主校验枚举 + 重算该列统计）；ProfileTable 类型下拉与七列统计口径（均值/中位数/q25/q75/最大/最小/计数）
- 不做：批量导入类型模板、跨工作区类型记忆

## 行为列表（TDD 循环队列）

- [x] B1: 整数列且唯一值≤10 推断为 ordinal 建议；普通数值列 continuous；字符串列 categorical
- [x] B2: PATCH 修改列类型后画像更新且非法类型返回 400
- [x] B3: 七列统计口径：n/mean/median/q25/q75/min/max（describe 与画像一致）
- [x] B4: categorical describe 输出频数表（top/频次/占比）

## 验收标准

- [硬门] B1–B4 pytest GREEN，既有测试回归通过

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B1 | `profiler.profile_dataframe` | `tests/test_typing.py` |
| B2 | `PATCH /sessions/{sid}/workspace/{dsid}/columns` | `tests/test_typing.py` |
| B3/B4 | `methods.describe` | `tests/test_typing.py` |

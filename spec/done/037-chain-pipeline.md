# 037 - 工作链增强二期（管道传递 / 类型置灰 / 模板导入导出）

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：033 原子工作链 + 034 模板

## 背景与目标

033 落地后工作链仍有两个缺口：① 链步骤间数据不流动（impute 的插补结果无法供后续步骤使用，
「插补→分析」套路必须拆成两次执行）；② 装配器对「数据列类型不适用」的工具无提示。
本 spec 补齐链间管道传递、类型置灰提示，并为模板增加导入导出（文件交换）。

## 范围

- 做：
  - 链间管道：impute 在 result 内部键 `_next_frame`（插补后 DataFrame）传递给后续步骤；
    executor 逐步替换当前 df；JSON 化前剥离该键（不进报告/前端）
  - 装配器置灰：数据列类型与 tool.accepts 完全不相交的工具下拉项 disabled + 后缀「（类型不适用）」
  - 装配提示：链含 impute 步骤时显示「后续步骤将使用插补数据」
  - 模板导入导出：`GET /templates/{name}/export`（JSON 附件）、`POST /templates/import`
    （复用 PUT 校验；重名 409，前端确认后带 `overwrite=true` 重发）
- 不做（YAGNI）：任意工具的通用输出→输入绑定（仅数据产出型工具管道化）；模板分类标签

## 行为列表（TDD 循环队列）

- [x] B1: 链「impute→describe」中 describe 作用于插补后数据（missing_after=0 体现）
- [x] B2: 单独 impute 步骤（无后续）行为不变；非 impute 步骤不产生 `_next_frame`
- [x] B3: `_next_frame` 不出现在报告 JSON（result/table 均无）
- [x] B4: `GET /templates/{name}/export` 返回 JSON 附件（name/steps 完整）
- [x] B5: `POST /templates/import` 创建模板；重名且未 overwrite → 409；带 overwrite → 覆盖
- [x] B6: 装配器：列类型与 accepts 不相交的工具置灰；链含 impute 时显示管道提示；模板导入导出 UI 可用

## 验收标准

- [硬门] B1–B6 确定性测试通过；既有测试全绿；覆盖率不回退
- [软标] 置灰工具在 tooltip 中给出当前数据类型与所需类型

## 契约与测试映射

| 行为 | 接口 | 测试 |
|---|---|---|
| B1–B3 | registry/executor | `tests/test_chain_pipeline.py` |
| B4–B5 | templates 路由 | `tests/test_templates.py` 追加 |
| B6 | ChainBuilder | `src/builder/ChainBuilder.test.tsx` 追加 |

# 048 工作链推荐模板与 AI 一键匹配

- 状态：done（2026-11-20 落地）

## 问题

内置方法学 skills 只作用于「讨论出方案」与「节点修正」，装配区仍是空白表单：
用户要自己知道「先描述再比较」「多组要事后校正」「生存要先 KM 再看 Cox」。
同时模板里的列位置是**语义**（分组列/随访时间/结局），无法直接写死成列名。

## 方案

- **推荐模板（recipe）**：`agents/chain_recipes.py` 内置 5 条按 skills 预设的流程
  （数据质量与基线 / 两组比较 / 多组 ANOVA+事后 / Logistic 影响因素 / 生存 KM+log-rank），
  节点全部是注册表工具，列位置用占位语义（`group`/`continuous_primary`/`time`/`event`/
  `binary_outcome`/`feature_list`）。
- **AI 一键匹配**：宿主先按占位语义 + 列类型/组数/取值筛出**候选列**（确定性），
  模型只在候选中做语义选择（`ChainMatchAgent`，单次结构化请求），宿主再复核候选合法性；
  模型不可用/失败 → 回退规则匹配（取首个候选），响应标注 `matched[].by = ai|rule`。
- **可执行性**：匹配后逐步 `validate_step` 硬校验，不通过的步骤从推荐链移除并给 warning。
- **人为修改**：载入的步骤带来源标签（AI/规则），支持「编辑」回填左侧表单后就地替换该步。

## 接口

- `GET /templates/builtin` → 模板目录（含占位中文标签、steps、slots）
- `POST /sessions/{sid}/chain/match {recipe_id, use_ai}` → `{ai, steps, matched, warnings}`

## 测试映射

| 行为 | 测试 |
|---|---|
| 模板节点必须存在于注册表 | `tests/test_chain_recipes.py::test_recipes_use_registered_tools_only` |
| 规则匹配产出可执行步骤 | `test_rule_match_produces_executable_steps` |
| 模型选择只接受候选内列 | `test_model_choice_accepted_only_when_in_candidates` |
| 缺列跳过 + warning | `test_missing_slot_skips_step_with_warning` |
| 接口（目录/匹配/兜底/400） | `test_builtin_recipes_endpoint` 等 4 项 |
| 前端载入/来源标注/编辑替换/提示 | `frontend/src/builder/ChainBuilder.recipes.test.tsx` 4 项 |

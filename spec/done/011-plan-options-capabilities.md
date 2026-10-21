# 011 - 方案选项式交互与能力披露

> 状态：done
> 创建：2026-10-18 ｜ 敲定：2026-10-18 ｜ 完成：2026-10-18

## 背景与目标

用户要求：方案提出后以选项框交互，选项下支持"自定义"与"补充对话"；并在前端披露 agent 具备的统计与绘图能力。

## 范围

- 做：`AnalysisPlan.options`（id/label/action/description，宿主保证唯一、必含 confirm、≤4）；工具目录注入模型 info；`GET /capabilities`（方法/必填参数/图表/规划中能力）；WS `option` 路由（confirm→执行，revise/explain/custom/supplement→回讨论）；前端能力抽屉、方案选项按钮组与补充输入
- 不做：选项级的参数表单生成（当前以自然语言补充）

## 行为列表（全部 GREEN）

- [x] B1: `GET /capabilities` 返回 10 个方法、图表类型与 planned 能力
- [x] B2: `option=confirm` 等价确认执行
- [x] B3: `option=explain/supplement`（可带文本）回讨论并生成新方案
- [x] B4: 未知 option_id → `INVALID_PARAM`
- [x] B5: 模型未给 options 时宿主补默认 confirm；重复 id 去重；非法 action 拒绝
- [x] B6: 工具目录（含必填参数）注入模型 info，缺参计划在讨论阶段被拒

## 契约

`PlanOption{id,label,action,description}`；`GET /capabilities{tools,charts,planned,methodology}`；`option{option_id,content?}`。

## 测试映射

`tests/test_capabilities.py`（4 项）、`tests/test_discussion.py`（4 项新增），前端 `npm run build` 通过，真实模型生成 4 选项（confirm/revise/explain/supplement）。

## 依赖与影响

依赖 009 注册表；前端消费 capabilities 与 options。规划中能力（生存分析/多重插补/多重性校正）显式披露为 planned，避免过度承诺。

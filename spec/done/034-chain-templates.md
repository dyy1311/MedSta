# 034 - 工作链模板保存与复用

> 状态：done
> 创建：2026-11-16 ｜ 敲定：2026-11-16 ｜ 完成：2026-11-16
> 上游：033 原子统计工作链的产品闭环（装配成果沉淀为可复用资产）

## 背景与目标

033 落地后用户可装配原子工作链，但装配成果是一次性的——下次分析需重新配置。
本 spec 让工作链可保存、命名、载入、删除，使「装配」成为可复用资产：
常用分析套路（如「描述→正态性→两组比较」）一次配置，反复使用。

## 范围

- 做：
  - 模板 CRUD：`GET/PUT/DELETE /templates[/{name}]`，存储于 `data_root/templates/*.json`（原子写）
  - 模板结构：`{name, steps, created_at, updated_at}`；steps 结构与 `run_chain` 一致
  - `tool_catalog` 输出补充 `accepts`（工具可接受的列类型），为后续预过滤提供数据
  - 前端装配 Tab：「我的工作链」区——保存（命名）/ 载入 / 删除；目标列快捷勾选（按列类型）
- 不做（YAGNI）：
  - 模板分享/导入导出文件、模板分类标签、跨用户隔离（单机单用户假设）
  - 装配工具按列类型硬过滤/置灰（需 accepts + 列类型联动，本轮仅提供数据）
  - 链步骤间数据传递（管道化）

## 行为列表（TDD 循环队列）

- [x] B1: `PUT /templates/{name}` 保存步骤链；`GET /templates` 列表可见且含 steps
- [x] B2: 同名重复 PUT 覆盖旧内容
- [x] B3: `DELETE /templates/{name}` 后从列表消失；删除不存在的模板返回 404
- [x] B4: 非法模板名（含路径分隔符/`..`）返回 400，不落盘
- [x] B5: steps 含未注册方法时返回 400
- [x] B6: 前端装配 Tab 可命名保存当前工作链，模板列表可载入（步骤回填编辑器）与删除

## 验收标准

- [硬门] B1–B6 确定性测试通过；后端/前端既有测试全绿
- [硬门] 模板写入为原子操作（复用 tmp+replace），损坏模板文件不导致列表接口失败
- [软标] 模板名支持中文；`updated_at` 随覆盖更新

## 契约与测试映射

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | `PUT /templates/{name}` + `GET /templates` | `tests/test_templates.py::test_save_and_list` |
| B2 | 同名 PUT | `tests/test_templates.py::test_overwrite_same_name` |
| B3 | `DELETE /templates/{name}` | `tests/test_templates.py::test_delete_template` |
| B4 | 非法 name | `tests/test_templates.py::test_rejects_unsafe_name` |
| B5 | steps 方法校验 | `tests/test_templates.py::test_rejects_unknown_method` |
| B6 | 前端装配 Tab | `src/builder/ChainBuilder.test.tsx` 新增用例 |

## 依赖与影响

- 依赖：`session/persistence.py` 的原子写模式（新 `templates.py` store 或独立实现）
- 新增 `api/routes_templates.py` 并挂载；`tool_catalog` 增加 `accepts` 字段（`test_method_contract` 不受影响，目录字段为追加）
- 前端：`ChainBuilder` 增加模板区与快捷勾选（需 `columnTypes` 新 prop，App 传入）

# 033 - 原子统计工作链装配（用户主权）+ JSON 输出契约 + 多格式导出

> 状态：done
> 创建：2026-11-16 ｜ 敲定：2026-11-16 ｜ 完成：2026-11-16
> 产品定位调整：从「模型驱动管线」转向「用户装配原子工具链」；断线重连顺延至 034。

## 背与目标

用户要求：**不灌管线灌流程**。每个统计分析指令都工具化为原子统计工具（registry 已是
单一真相源，22 个 ToolSpec 即原子单位）；模型只提出统计建议（拆分为原子工具组成的
工作链草稿），**用户自行装配、确认后执行**。所有分析数据输出为 JSON（工具输出硬要求），
前端一律以表格/图呈现，下载支持 JSON/CSV/XLSX（表格）与 PNG/JPG/PDF/TIF（图）。
`docs/tools.md` 登记全部统计/作图工具。

## 范围

- 做：
  - WS `run_chain` 事件：用户装配的原子工具链（method/target_columns/chart_type/params）→
    宿主 `validate_plan` 硬校验 → 构造手动 `AnalysisPlan` → 复用既有执行/审阅/交付流
    （图表在装配时已选定，**跳过 chart_config 暂停**）；无模型参与也可执行
  - 模型建议作为装配起点：plan 事件的 steps 可一键导入链编辑器继续增删改
  - JSON 输出硬门：registry 全部工具 handler 输出可 `json.dumps(allow_nan=False)`（契约测试）
  - 导出扩展：表格 `format=json`（完整步骤 JSON：result+table+meta）；图 `format=jpg|pdf|tif`
    （按需重渲染，与既有 png 并存）
  - `docs/tools.md`：登记全部统计/作图工具，与 registry/CHART_TYPES 一致性守护测试
  - 前端「工具装配」Tab：工具选择（按分类）→ 参数表单（按 ToolSpec 动态生成）→ 目标列/图表
    选择 → 工作链编辑（上移/下移/删除）→ 执行；表格与图卡下载菜单扩展
- 不做（YAGNI）：
  - 链步骤间数据传递（管道输出→下一步输入）：每步独立作用于当前激活数据集（既有语义）
  - 工作链模板保存/命名/复用（后续 spec）
  - 聊天消息流回放与 WS 断线重连（034）
  - 表格 PDF 导出（图支持 pdf；表格 PDF 需排版引擎，后续评估）

## 行为列表（TDD 循环队列）

### 后端

- [x] B1: registry 全部统计工具的 handler 输出可 `json.dumps(allow_nan=False)` 序列化
      （逐工具最小合法输入采样，NaN/Inf/numpy 类型为硬失败）
- [x] B2: `run_chain` 合法两步链 → progress → review_request（报告含两步），session.plan 为手动计划，全程无 chart_config 暂停、无模型调用
- [x] B3: `run_chain` 校验失败（未知方法/缺必填参/目标列不足）→ INVALID_PLAN 错误帧带 issues 明细，不产生执行
- [x] B4: `run_chain` 状态约束：DELIVERED 态装配新链可执行（先回 discussing）；executing 中被 SESSION_BUSY 拒绝
- [x] B5: 表格导出 `format=json` 返回完整步骤 JSON（result/table + meta：tool/title/step_index/report_id），Content-Type 为 application/json
- [x] B6: 图导出 `format=jpg|pdf|tif` 返回对应 Content-Type 的非空文件（按需重渲染）
- [x] B7: `docs/tools.md` 登记全部统计工具与作图类型，与 registry/CHART_TYPES 双向一致（守护测试）

### 前端

- [x] B8: 「工具装配」Tab：按分类选择工具 → 参数表单按 ToolSpec 动态渲染（column/column_list/choice/integer/boolean/string）→ 添加步骤进工作链
- [x] B9: 工作链编辑：步骤上移/下移/删除；执行发送 `run_chain`（含全部步骤参数）
- [x] B10: 方案导入：plan 事件的 steps 一键填入链编辑器（可继续编辑）
- [x] B11: 下载扩展：表格行新增 JSON 下载链接；图卡新增 JPG/PDF/TIF 下载项

## 验收标准

- [硬门] B1–B7 确定性测试全绿；B8–B11 Vitest 组件测试全绿
- [硬门] JSON 契约为持续硬门：新增工具不通过 B1 式序列化检查无法合入
- [硬门] 手动链全程零模型调用（fake_agent 缺席下 run_chain 可完整走通）
- [软标] 装配体验：工具按 sta_task/分类分组、参数带教材口径提示（applicability/method_note 透出）
- [软标] tools.md 可读性（分类分节、含适用条件与图表支持）

## 契约与测试映射

新增 WS 入站事件（唯一新增契约）：

```
run_chain: {type:"run_chain", steps:[{method, target_columns, chart_type, params}]}
→ 校验失败: {type:"error", code:"INVALID_PLAN", detail:{issues:[...]}}
→ 成功: 复用既有 progress → review_request → delivered 流（无 chart_config）
```

出站事件无新增；`report` 增加 `report_id`（032 已有）。导出新增 `format=json|jpg|pdf|tif`。

| 行为 | 公共接口 | 测试文件 / 用例 |
|---|---|---|
| B1 | registry 全 handler | `tests/test_json_contract.py::test_every_tool_output_is_strict_json` |
| B2 | WS `run_chain` | `tests/test_tool_chain.py::test_run_chain_executes_without_model` |
| B3 | WS `run_chain` 非法 | `test_tool_chain.py::test_run_chain_rejects_invalid_steps` |
| B4 | WS `run_chain` 状态 | `test_tool_chain.py::test_run_chain_state_guards` |
| B5 | GET export format=json | `tests/test_export_delivery.py::test_export_step_as_json` |
| B6 | GET export format=jpg/pdf/tif | `test_export_delivery.py::test_export_chart_formats` |
| B7 | docs/tools.md | `tests/test_docs_consistency.py::test_tools_md_matches_registry` |
| B8/B9 | ChainBuilder 组件 | `frontend/src/builder/ChainBuilder.test.tsx` |
| B10 | 方案导入 | `ChainBuilder.test.tsx::import plan steps` |
| B11 | 下载菜单 | `WorkspacePanel.test.tsx` / `ChartCard` 扩展 |

## 依赖与影响

- 依赖：registry `tool_catalog`（参数披露）、`validate_plan`（宿主校验）、`_execute_plan`（执行复用）、
  `/capabilities`（前端数据源）、032 的 report_id
- 修改：`api/ws.py`（无改动，兜底已就绪）、`session/service.py`（`_on_run_chain`）、
  `pipeline/executor.py`（无需改）、`api/routes_export.py`（格式扩展）、`stats/plotting.py`（渲染 format 参数）、
  `docs/tools.md`（新）、`test_docs_consistency.py`（新增断言）
- 前端：`App.tsx`（第三 Tab）、`builder/ChainBuilder.tsx`（新）、`WorkspacePanel`/`ChartCard`（下载扩展）
- Owner 划分不变：装配参数的语义合法性仍由宿主 `validate_plan` 裁决，模型仅产出建议草稿

## 备注

- run_chain 的 PlanStep 由宿主构造（step_id/rationale 宿主生成），模型不参与 → 无方案校验重试环
- JSON 硬门实现为独立契约测试文件，遍历 `_REGISTRY` 全部键；样本数据覆盖数值/分组/二分类/生存/设计期工具
- 图多格式导出用 matplotlib savefig 原生支持（pdf/jpg/tif 依赖 pillow，已在依赖树内）；按需重渲染而非预生成，避免存储膨胀

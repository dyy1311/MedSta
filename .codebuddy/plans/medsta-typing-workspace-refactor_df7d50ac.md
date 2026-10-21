---
name: medsta-typing-workspace-refactor
overview: 修复工作台追加导入；重定义会话（LLM 交互）/工作区（数据、表格交付、图表）语义；引入变量类型槽位（连续/等级/类别/序列索引）+ 用户可编辑画像 + 前置类型确认节点；按变量类型驱动统计方法与图表映射；统计口径改为均值/中位数/q25/q75/最大/最小/计数；表格型交付进工作区并追问是否绘图。
todos:
  - id: spec-drafts-015-017
    content: 起草 spec/implementing/015-column-typing.md、016-type-driven-mapping.md、017-workspace-delivery.md（行为列表/验收/测试映射），呈现确认后进入 implementing
    status: completed
  - id: fix-workspace-import
    content: 用 [skill:tdd] 修复工作区"+"导入：WorkspacePanel 内嵌隐藏 file input，uploadData 后新建 Tab 并激活；ChatPanel 仅在无工作区时显示 UploadZone
    status: completed
  - id: typing-system
    content: 用 [skill:tdd] 实现 profiler 四类类型推断 + PATCH columns 端点 + ProfileTable 类型下拉（continuous/ordinal/categorical/index）+ 七列统计口径（均值/中位数/q25/q75/max/min/n）
    status: completed
    dependencies:
      - spec-drafts-015-017
  - id: type-gate
    content: 用 [skill:tdd] 实现 type_review/type_confirm 前置节点：未确认类型时 chat 被拦截并下发类型确认卡，确认后缓存 chat 自动继续
    status: completed
    dependencies:
      - typing-system
  - id: type-driven-mapping
    content: 用 [skill:tdd] 实现 ToolSpec.accepts 校验（COLUMN_TYPE_MISMATCH/ordinal 降级提示）、describe 双形态统计与频数表、default_chart_for 类型→图表映射并接入 chart_config options
    status: completed
    dependencies:
      - typing-system
  - id: delivery-workspace
    content: 用 [skill:tdd] 实现表格交付进工作区（工作区渲染表格卡+导出）与 plot_suggest/plot_later 补绘图流程
    status: completed
    dependencies:
      - type-gate
  - id: frontend-semantics
    content: 前端语义重构：会话区精简为交互摘要，工作区承载画像/表格/图表；ReviewCard 改摘要卡，npm run build 通过
    status: completed
    dependencies:
      - delivery-workspace
  - id: e2e-verify
    content: 真实模型端到端：上传→类型确认（改一列类型）→讨论→执行→工作区表格交付→补绘图询问→导出；pytest 全绿
    status: completed
    dependencies:
      - frontend-semantics
  - id: governance-update
    content: 三个 spec 迁 done，更新 statistics-methods.md（类型映射）、timeline、TO_DO.md、CODEBUDDY 与 README
    status: completed
    dependencies:
      - e2e-verify
---

## 需求概述

针对 MedSta 数据分析智能体的 6 项体验与能力升级（用户要求顺序：先 spec 确认 → 补 tools → 改 agent 编排）：

1. **工作台"+"导入未实装**：点击 + 号后不能导入（当前 ChatPanel 在 uploaded 后隐藏 UploadZone，WorkspacePanel 的 + 仅切回会话 Tab）
2. **会话与工作区语义重定义**：会话=与 LLM 交互区域；工作区=数据交付、统计表展示、数据展示、数据操作、图片操作区域
3. **变量类型槽位**：四类（整数值-连续型 / 数值-等级型 / 类别型 / 序列索引，统计中通常排除序列索引）；数据画像中每列类型可用户手动修改（下拉菜单）；关键统计展示改为均值、中位数、q25、q75、最大、最小、计数
4. **变量类型驱动方法映射**：类型槽位作为统计方法选择与图表形式的重要参考（调整映射策略）
5. **前置类型确认节点**：统计意图分析与方法选择前，先做变量类型判断并提示用户敲定
6. **方案选项结果体验修正**（截图反馈）：选项执行后结果仍是 JSON 直出、未在工作区做表格展示、无进一步"是否绘图"询问

交付物含三份 spec（015 类型系统与前置确认、016 类型驱动映射与统计口径、017 工作区语义重构与导入/交付/绘图追问），先确认再实施；实现顺序：spec → tools → agent 编排 → 前端 → 端到端 → 治理。

## 核心功能

- **导入修复**：工作区"+"直接弹出文件选择并上传为新工作区（不经会话 Tab）
- **类型系统**：`continuous/ordinal/categorical/index` 四类；profiler 推断建议 + 用户下拉修正；index 类型默认排除出统计
- **前置确认节点**：chat 前若工作区未敲定类型，下发 `type_review` 事件（建议类型表）→ 用户确认/修改 → 进入讨论
- **类型驱动映射**：ToolSpec 声明支持的列类型；validate_step 按类型拒绝（ordinal 降级提示非参数）；describe 按 continuous/categorical 输出不同统计与频数表；关键统计展示改为均值/中位数/q25/q75/最大/最小/计数
- **表格交付进工作区**：执行完成的工作区渲染结果表格卡（含 CSV/XLSX 导出），会话流仅摘要
- **绘图追问**：表格型步骤交付后服务端发 `plot_suggest`（可选图表类型列表），前端确认 `plot_later` 后单步补渲染并更新报告

## 视觉与体验

会话区保留聊天流与方案卡；工作区顶部 Tab + 列类型下拉（每列徽标变为可编辑 select）；统计表卡仅展示均值/中位数/q25/q75/max/min/n 七列；交付区出现"是否绘图？"确认条（图表类型单选 + 确认/跳过）。

## 技术栈

沿用现有：Python 3.12（mamba Sta）+ FastAPI + Agently + pandas/scipy/statsmodels；React 18 + TS + Vite 5 + Tailwind 3。

## 技术方案

### 1. 类型系统（spec 015）

- `data/profiler.py`：`ColumnMeta.type` 扩展为 `continuous/ordinal/categorical/datetime/boolean/index`（infer 建议：纯整数且唯一值≤10 → 建议 ordinal；非数值 → categorical；datetime → index 候选）；`TableProfile.type_confirmed: bool = False`
- `PATCH /sessions/{sid}/workspace/{dsid}/columns`（body: `{column: type}`）：宿主校验枚举，更新 profile 并重算该列统计（ordinal/categorical 转换列统计形态）
- 前端 ProfileTable：类型徽标改下拉（select），变更即调 PATCH 并刷新画像

### 2. 类型驱动映射与统计口径（spec 016）

- `ToolSpec` 增加 `accepts: tuple[str, ...]`（可接受的列类型集合，如 group_compare targets 需含 continuous；chi_square 需 categorical；timeseries 需 continuous；index 列一律拒绝并提示）
- `validate_step` 增加 `COLUMN_TYPE_MISMATCH` issue（ordinal 用于参数检验时降级提示走非参数）
- `methods.describe`：continuous 输出均值/中位数/q25/q75/max/min/n（去掉 sd 或保留可选）；categorical 输出频数表（top/频次/占比）→ `table`
- `plotting.default_chart_for(column_type, method)`：类型→默认图（continuous→histogram/boxplot；categorical→bar/pie；ordinal→bar）；`chart_config` 的每步 options 按列类型过滤
- 模型 info 注入的类型摘要同步更新（每列类型 + 建议用途）

### 3. 前置确认与交付追问（spec 017）

- `SessionData.type_confirmed: bool`；`service._on_chat` 前置：未确认 → 发 `{"type":"type_review","dataset_id","columns":[{name,type,suggestions}]}` 并返回（不调模型）
- WS `type_confirm` 事件：携带用户修改后的列类型映射 → 保存 → `{"type":"type_confirmed"}` → 自动继续原 chat（缓存 pending_chat）
- 执行交付后：对"有 table 但无 artifact"的步骤，在 review_request 后追加 `{"type":"plot_suggest","step_index","charts":[...]}`；前端确认 `{"type":"plot_later","step_index","chart_type"}` → 单步补渲染（复用 render_chart）→ 更新报告并重发 review_request
- 导入修复：WorkspacePanel "+" 触发隐藏 file input → `uploadData` → 新 Tab；ChatPanel 的 UploadZone 仅在无任何工作区时显示

### 4. 前端语义调整

- 会话区=纯交互（消息/方案/错误/配置卡）；工作区=Tab（画像+类型编辑、结果表格卡+导出、图表卡、下载）
- ReviewCard 精简为摘要卡（步骤状态 + 图表链接 + "去工作区查看"），完整表格移至工作区

## 实现顺序

spec 落盘 → tools（registry 校验/methods 统计口径/plotting 默认图）→ service（type_review/type_confirm/plot_suggest/plot_later）→ 前端 → 端到端 → 治理

### Skill

- **tdd**：类型推断与校验、类型驱动映射、type_review/plot_suggest 流程、导出端点均按 RED-GREEN 垂直切片实施
- **agently-request**：讨论上下文注入列类型摘要与槽位说明，保证模型按类型选方法
- **agently-triggerflow**：plot_later 单步补渲染作为审阅后追加节点接入既有编排
- **agently-design**：核对"模型选方法、宿主按列类型校验、用户敲定类型"的所有权边界
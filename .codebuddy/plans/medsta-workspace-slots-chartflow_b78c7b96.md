---
name: medsta-workspace-slots-chartflow
overview: 修复能力披露加载失败（vite 代理缺 /capabilities），将统计工具槽位化（sta_task/group_col/value_col/agg + 正态性→方差齐性→最优/次优检验策略链），新增多工作区（多表格分页）、出图前交互（图表类型与画板布局确认、饼图）、可视化表格交付与 Excel/CSV 导出、思考过程折叠；按"先 spec、再 tools、后 agent 编排"顺序以 TDD 实施。
design:
  architecture:
    framework: react
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 24px
      weight: 600
    subheading:
      size: 16px
      weight: 500
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#3B5BDB"
      - "#1E2A5A"
      - "#22B8CF"
    background:
      - "#F7F8FB"
      - "#FFFFFF"
    text:
      - "#1A1D2B"
      - "#6B7280"
    functional:
      - "#2F9E44"
      - "#E03131"
      - "#F08C00"
todos:
  - id: spec-drafts
    content: 起草 spec/implementing/012-multi-workspace.md、013-slot-tools-test-strategy.md、014-chart-confirm-delivery.md（含行为列表/验收/测试映射），按用户要求先呈现确认
    status: completed
  - id: fix-capabilities-proxy
    content: 修复 vite proxy 增加 /capabilities 与 fetchCapabilities 容错，dev 冒烟验证能力抽屉可加载
    status: completed
  - id: tools-slot-strategy
    content: 用 [skill:tdd] 槽位化 registry（task/slots 字段、校验）并新增 levene_test、aggregate_table、pie 图表；group_compare/anova 实现"正态性→Levene→不平衡提示→最优/次优"策略链并输出 strategy
    status: completed
    dependencies:
      - spec-drafts
  - id: multi-workspace-backend
    content: 用 [skill:tdd] 实现 Session 多数据集（datasets/active_dataset_id）、上传返回 dataset_id、激活接口；chat/confirm 作用于激活工作区
    status: completed
    dependencies:
      - spec-drafts
  - id: agent-orchestration
    content: 用 [skill:agently-request] 改造 discussion：统计任务拆解链提示（sta_task→分组→值→方法→策略）、step_id、槽位注入与校验
    status: completed
    dependencies:
      - tools-slot-strategy
      - multi-workspace-backend
  - id: chart-flow-backend
    content: 用 [skill:agently-triggerflow] 实现出图确认暂停（chart_config/chart_choice）、pie 与 shared/separate 画板渲染、可视化表格序列化与 /export CSV/XLSX 端点
    status: completed
    dependencies:
      - agent-orchestration
  - id: frontend-upgrade
    content: 前端：工作区分页 Tab、思考过程折叠、图表配置卡、可视化交付表格 + Excel/CSV 导出按钮，npm run build 通过
    status: completed
    dependencies:
      - chart-flow-backend
  - id: e2e-verify
    content: 真实模型端到端：多表格上传切换、槽位化方案、出图确认（改图表类型+拼图）、表格交付与导出、能力披露正常；pytest 全绿
    status: completed
    dependencies:
      - frontend-upgrade
  - id: governance-update
    content: 三个 spec 迁 done，更新 statistics-methods.md（策略链与槽位）、timeline、TO_DO.md、CODEBUDDY（含变更记录规则）与 README 能力说明
    status: completed
    dependencies:
      - e2e-verify
---

## 需求概述

针对 MedSta 数据分析智能体的体验与能力升级（用户要求顺序：先 spec 确认 → 补 tools → 改 agent 编排）：

1. **能力披露报错修复**：dev 下 `GET /capabilities` 落在 Vite 自身返回 HTML（vite.config.ts proxy 缺 `/capabilities`），导致"目录加载失败"
2. **多工作区分页**：每个上传表格为独立工作区，可上传多个表格，通过分页 Tab 切换当前工作区；讨论与执行针对激活工作区
3. **思考过程可折叠**：流式思考气泡支持展开/收起
4. **出图前确认**：方案确认后、渲染前向用户确认
5. **可视化表格交付**：结果不再直出 JSON，改为可视化表格卡片，提供 Excel/CSV 导出按钮
6. **绘图类型询问**：出图前询问图表类型（箱线/折线/柱状/饼图/散点/提琴等），新增饼图
7. **统计任务槽位化与检验策略链**：工具以 `sta_task` + 槽位（group_col/value_col/agg 等）声明；方案必须先想清"统计任务→分组变量→值变量→方法"；检验自动走"正态性→方差齐性→不平衡提示→最优方法→次优降级"策略链
8. **多图画板询问**：多个图时询问同画板拼图还是分别出图
9. **卡方数据量分析**：chi_square 输出期望频数分析（每格期望、最小期望、期望<5 占比）→ 2×2 不足自动改用 Fisher；R×C 不足建议增大样本/合并类别；结构化 strategy 字段
10. **显著性分析规范**：判断前先与用户讨论 p 值界限（α 默认 0.05，可在配置中选择）；报告表格必须含统计量、p 值、显著性标注（星号 + 是否达 α）；出图标注显著性；多重检验交付总体 + 两两分析（Holm/Bonferroni 校正后显著性）并特别提醒 p 值修正问题
11. **（本次补充）选择依据显式化**：**所有统计方案与检验方案的选择必须显式解释原因和说明依据**——

    - 工具目录中每个方法声明"适用条件"（什么样的数据/任务适合用它）
    - `PlanStep` 增加 `rationale` 字段：模型必须为每个步骤写明选择依据（数据类型、任务性质、样本特征、方法适用性）
    - 执行期策略链的每一步判定（正态性/方差齐性/期望频数/失衡）都记录进 `strategy.steps[]`，最终方法与次优建议可追溯
    - 前端方案卡逐步骤展示依据（可展开）；交付卡展示策略链判定过程

交付物含三份 spec（012 多工作区+能力修复、013 槽位化工具与检验策略链、014 出图交互与表格交付），先确认再实施。

## 技术方案

### 1. 能力披露修复（012 前置，快速修复）

- `frontend/vite.config.ts` proxy 增加 `"/capabilities": "http://localhost:8000"`；`fetchCapabilities` 增加 response.ok 与 content-type 校验

### 2. 多工作区（spec 012）

- 后端：`Session.data` → `datasets: dict[dataset_id, SessionData]` + `active_dataset_id`；上传返回 dataset_id；`POST /sessions/{id}/workspace/{dataset_id}/activate`；chat/confirm 作用于激活工作区
- 前端：工作区 Tab 条（数据集名 + 激活态，"+"追加上传）；reports 按 dataset_id 分组

### 3. 槽位化工具与检验策略链（spec 013）

- `ToolSpec` 增加 `task`、`slots`、**`applicability`（适用条件文本，进 tool_catalog 与模型 info）**；槽位缺失即 MISSING_PARAM
- 新工具：`levene_test`、`aggregate_table`、`pie` 图表
- 连续变量策略链（group_compare/anova）：逐组 Shapiro → Levene → 失衡提示 → 最优方法（正态+齐性=t/ANOVA；正态+不齐=Welch；非正态=MWU/Kruskal）→ 次优建议 → `strategy{steps[], final_method, alternative}`
- 卡方策略链：期望频数分析 → 占比≤20% 且最小期望≥1 用卡方；2×2 超出自动 Fisher；R×C 超出建议增大样本/合并类别；类别 n<5 不平衡提示 → `strategy`
- 显著性规范：`significance_label(p, alpha)` → `{significant, stars}`；所有检验结果含 `alpha/significant/stars`；`table` 列含 statistic/p_value/significance；anova ≥3 组输出 `overall + pairwise`（Holm 默认校正，可选 bonferroni/none）+ 多重性提醒文案；α 与 correction 为执行配置（014 配置卡），缺省 0.05/holm

### 4. 出图交互与表格交付（spec 014）

- 出图确认流：`chart_config` 事件（每步默认图表 + 可选类型含 pie + 多图布局 + α/校正配置）；`chart_choice` 回填后执行；跳过用默认
- 显著性绘图：boxplot/violin/grouped_bar 组间比较线 + 星号/ns 标注
- 可视化交付：`StepResult.table`（columns+rows）；`GET /export/{session_id}/{step_index}?format=csv|xlsx`；前端表格卡 + 下载按钮 + JSON 折叠
- 思考折叠：完成后转一行摘要 + Chevron
- **依据显式化（本次补充）**：
- `_BASE_INSTRUCT` 改为统计任务拆解链（sta_task→分组→值变量→方法→检验策略→显著性规范），**强制每个步骤填写 rationale（为何选此方法/参数，基于数据类型与画像特征）**，缺失 rationale 由宿主拒绝（MISSING_PARAM 语义）
- 方案卡逐步骤展示 rationale（默认折叠，可展开）；交付卡展示 `strategy.steps[]` 判定过程与次优建议；能力抽屉展示每个方法的适用条件

### 5. 实现顺序

spec 落盘 → tools（registry/methods/plotting，显著性工具函数与 applicability 优先）→ agent 编排 → 前端 → 端到端验证 → 治理收尾

前端新增交互：

- **工作区 Tab 条**：横向分页 + 激活高亮 + "+"追加上传
- **分析配置卡**：图表类型单选、多图画板二选一、α 与校正方法选择、"开始执行 / 跳过用默认"
- **可视化交付卡**：斑马纹表格（含显著性列）+ CSV/Excel 下载 + JSON 折叠 + 多重检验黄底提醒条 + **策略链判定过程展示（每步依据 + 次优建议）**
- **方案卡依据展示**：每步骤下方"选择依据"折叠区（rationale）
- **思考折叠**："思考过程 · N 字" + Chevron
- **能力抽屉**：方法卡增加"适用条件"文本

### Skill

- **tdd**：槽位校验、策略链（含卡方数据量分析）、显著性标注、pairwise+校正、rationale 强制校验、多工作区、chart_choice 路由、导出端点均 RED-GREEN 垂直切片
- **agently-request**：槽位契约与工具目录（含适用条件）注入、统计任务拆解链提示
- **agently-triggerflow**：出图确认复用 pause_for 暂停语义接入 TriggerFlow
- **agently-design**：模型选槽位并给依据、宿主校验执行、策略链确定性的所有权边界
---
name: medsta-stats-tools-and-ux
overview: 修复统计脚本参数对齐崩溃，按医学统计方法论将统计方法固化为带参数契约的工具库（9 类方法 + 10 类图表、宿主动态校验），并实现错误可见、流式输出、中断/继续、能力披露与方案选项式交互（后端 WS 协议 + 前端 UI）。
design:
  architecture:
    framework: react
  fontSystem:
    fontFamily: PingFang-SC
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
      - "#1E2A5A"
      - "#3B5BDB"
      - "#22B8CF"
    background:
      - "#F7F8FB"
      - "#FFFFFF"
    text:
      - "#1A1D2B"
      - "#6B7280"
      - "#FFFFFF"
    functional:
      - "#2F9E44"
      - "#E03131"
      - "#F08C00"
todos:
  - id: spec-stats-tools
    content: 创建 spec 009 并落地统计工具库：`stats/registry.py` 契约与校验、10 个方法实现、中文字体配置、executor 注册表派发，用 [skill:tdd] 先写参数缺失与图表断言
    status: completed
  - id: fix-plan-validation
    content: 改造 `agents/discussion.py`：method/chart 改由注册表校验、工具目录注入 info、新增 options 字段与宿主校验，用 [skill:tdd] 覆盖缺参返回结构化错误
    status: completed
    dependencies:
      - spec-stats-tools
  - id: realtime-control
    content: 实现错误码体系、`[skill:agently-request]` 流式网关、会话任务化与中断/继续事件、步骤进度，用 [skill:tdd] 验证中断取消与恢复审阅
    status: completed
    dependencies:
      - fix-plan-validation
  - id: options-capabilities-api
    content: 新增 `GET /capabilities` 与 WS option 事件路由（confirm/revise/explain/custom），用 [skill:agently-design] 核对所有权边界后补测试
    status: completed
    dependencies:
      - realtime-control
  - id: frontend-interaction
    content: 扩展前端类型与 WS 客户端，新增能力抽屉、方案选项按钮组、流式气泡、中断/继续、错误卡片，完成 npm run build
    status: completed
    dependencies:
      - options-capabilities-api
  - id: e2e-verify
    content: 真实模型端到端冒烟：正常讨论执行交付、故意构造缺参方案验证错误可见、执行中断与继续、图表中文标题无缺字
    status: completed
    dependencies:
      - frontend-interaction
  - id: governance-update
    content: 三个 spec 迁入 done，补 `docs/statistics-methods.md` 方法映射与证据来源，更新 timeline、CODEBUDDY 与 README 能力说明
    status: completed
    dependencies:
      - e2e-verify
  - id: c1a72014
    content: 创建to_do.md每次随timeline记录
    status: completed
  - id: 4662f61c
    content: 将每次变更必须记录timeline并更新TO_DO记入CODEBUDDY开发规则
    status: completed
---

## 用户需求

修复统计脚本崩溃，并按医学统计方法论将统计能力固化为工具、补齐交互体验。

## 核心功能

- **崩溃修复**：`hypothesis_test` 硬取 `params["group_column"]` 导致 KeyError，链路中断并抛 ASGI 异常；图表中文标题字形缺失（Glyph missing）。改为宿主侧参数契约校验 + 中文字体配置，缺参不崩溃而是给出可读错误
- **统计工具库**：依据《医学统计处理流程图》《顶刊统计策略图谱》的终点类型决策表、缺失数据决策板，将统计方法固化为带参数契约与图表声明的工具：连续型（描述统计、正态性检验、两组比较、多组 ANOVA）、二分类（卡方、Logistic 回归）、关联预测（相关、线性回归、时间序列预测）、数据质检（缺失报告）
- **错误可见**：错误分类并可读呈现（模型未配置/模型请求失败/方案非法/缺少参数/引用不存在的列/工具不存在/执行失败/未上传数据/已中断），含错误码、说明、修复建议与可展开详情
- **流式输出**：模型思考与阶段进度以流式事件推送，前端逐字呈现，步骤执行显示进度
- **中断与继续**：对话与执行均可中断；中断后保留会话与数据，可继续审阅或继续对话
- **能力披露**：前端展示 agent 支持的统计方法、必填参数与图表类型，并在讨论时注入模型上下文
- **选项式交互**：方案卡片以选项按钮呈现（按此执行/更换方法/解释依据/自定义/补充对话），支持自定义说明直接回流讨论
- **开发方式**：spec 驱动 + TDD，新增 spec 走 implementing 到 done 生命周期并记录时间线

## 视觉与体验

方案卡片下方为按钮式选项组，选中即发送；补充对话展开输入框。顶栏新增“能力”入口，抽屉式展示方法卡与图表标签。执行中和生成中显示流式气泡与呼吸状态点，右侧提供中断按钮；错误以黄色/红色卡片呈现，含错误码与建议。

## 技术栈

沿用现有：Python 3.12（mamba Sta）+ FastAPI（REST/WebSocket）+ Agently（ModelRequest 流式）+ pandas/scipy/statsmodels/matplotlib；前端 React 18 + TS + Vite 5 + Tailwind 3。

方法学依据为项目内两份文档（八道门禁 G0–G7、四块决策板、终点类型决策表），未引入外部检索依赖。

## 实施策略

### 1. 统计工具库（新 spec 009）

新建 `backend/src/medsta/stats/registry.py`，定义可被模型识别、被宿主校验的单一真相源：

- `ToolParam(name, type, required, description, choices, default)`
- `ToolSpec(name, title, category, description, params, charts, handler)`
- `TOOL_REGISTRY`：describe、missing_report、normality_test、group_compare、anova、chi_square、correlation、regression、logistic_regression、timeseries_forecast
- `validate_step(step, profile) -> list[ToolIssue]`：方法不存在、列不存在、必填参数缺失、参数类型/取值非法、组数不足
- `execute_step(df, step, artifact_dir, index)`：统一派发，返回 `StepOutcome(result, artifact)`；异常归一为带 code 的错误

`executor.py` 由硬编码 dict 改为注册表派发；`AnalysisPlan` 的 method/chart_type 由固定 Literal 改为注册表校验（保留宿主权威），并新增 `step_id`。图表扩展 histogram/boxplot/violin/scatter/line/bar/grouped_bar/heatmap/qq_plot/residual_plot。

中文字体：新建 `stats/plotting.py`，检测可用 CJK 字体（Noto Serif/Sans CJK、WenQuanYi、SimHei）设置 `rcParams["font.sans-serif"]` 与 `axes.unicode_minus=False`；无 CJK 字体时标题回退英文映射，彻底消除缺字警告。

### 2. 实时交互（新 spec 010）

- `backend/src/medsta/errors.py`：`ErrorCode` 枚举 + `AppError(code, message, hint, detail)`；WS 错误统一 `{type:"error", code, message, hint, detail}`
- `config.py` 增补 `ModelGateway.stream_text(...)`：基于 `request.get_async_generator()` 转发 reasoning_delta/delta；异常分类为 MODEL_REQUEST_FAILED（保留 provider 摘要，不泄漏密钥）
- `session/service.py` 任务化：`_tasks[session_id]` 管理生成/执行任务；`{"type":"interrupt"}` 取消任务并 `workflow.cancel`，发 `{"type":"interrupted", stage}`；`{"type":"resume"}` 恢复：有暂停审阅则重发 review_request，否则回到讨论态
- 事件：`stream`（delta 文本）、`progress`（阶段与步骤 i/n）、`interrupted`、`resumed`
- 执行报告：每步 `status success/failed` + `error` 字段；前置校验不通过直接返回 INVALID_PLAN 清单，不进入执行

### 3. 选项交互与能力披露（新 spec 011）

- `AnalysisPlan` 增 `options: list[PlanOption{id,label,action(confirm|revise|explain|custom|supplement),description}]`；宿主保证含 confirm、id 唯一、action 在枚举内
- 工具目录序列化后写入请求 `.info`，模型据此选择方法与参数；`GET /capabilities` 返回方法/参数/图表目录供前端披露
- WS 新增 `{"type":"option","option_id"}`：confirm 走确认执行，revise/explain 走再讨论，custom/supplement 携带用户文本
- 前端：`CapabilityDrawer`（方法卡 + 图表标签 + 必填参数）、`PlanCard` 选项按钮组与补充输入、`ChatPanel` 流式气泡 + 中断/继续按钮、`ErrorCard`（错误码/建议/详情折叠）、`App` 状态机（idle/streaming/executing/interrupted/delivering）

### 性能与可靠性

- 工具校验为 O(步骤数 × 参数数)；执行仍为一次性向量化计算
- 流式仅转发增量文本，不重复整包上下文；中断使用 asyncio 任务取消与进程内清理，不泄漏子进程
- 兼容旧协议：保留 chat/confirm_plan/review 事件，新事件为增量扩展；用户首选确认路径无行为变化

## 架构与文件

```
backend/src/medsta/
├── errors.py                 # [NEW] 错误码与 AppError
├── stats/
│   ├── registry.py           # [NEW] ToolSpec/参数契约/校验/派发
│   ├── methods.py            # [NEW] 10 个统计方法实现
│   └── plotting.py           # [NEW] 字体配置与 10 类图表
├── pipeline/executor.py      # [MODIFY] 注册表派发、步骤错误捕获
├── agents/discussion.py      # [MODIFY] options、工具目录注入、流式草拟
├── config.py                 # [MODIFY] stream_text 与错误分类
├── session/service.py        # [MODIFY] 任务化/中断/继续/进度/option 路由
├── api/routes_capabilities.py# [NEW] GET /capabilities
└── app.py                    # [MODIFY] 挂载新路由

backend/tests/：test_stats_registry.py、test_executor.py、test_realtime.py、test_capabilities.py
frontend/src/：types.ts、api/client.ts、chat/ChatPanel.tsx、chat/PlanCard.tsx、chat/ErrorCard.tsx、chat/CapabilityDrawer.tsx、App.tsx
spec/implementing/：009-stats-tool-registry.md、010-realtime-control.md、011-plan-options-capabilities.md（完成后迁 done）
docs/statistics-methods.md  # [NEW] 方法论文档到工具的映射与证据来源
```

## 关键契约

- `ToolSpec` 是模型提示、前端披露、宿主校验、执行派发的唯一真相源，新增方法只改注册表
- `PlanStep.params` 的必填项由 `ToolSpec.params` 决定，缺参在讨论阶段即被拒绝并提示模型重试，执行期不再出现 KeyError
- WS 事件向后兼容：旧客户端忽略未知事件

## 设计方向

延续现有深靛蓝工作台风格，新增四类交互组件，保持信息密度与克制的数据工具气质。

## 页面与区块

**顶栏**：左侧品牌与“AI 数据分析工作台”，右侧新增“能力”按钮（打开能力抽屉），保留会话/工作区 Tab。

**能力抽屉**：右侧滑出玻璃质感面板，按“描述与质检 / 组间比较 / 关联与预测”分组列出方法卡（名称、一句话说明、必填参数标签、可用图表标签），底部图例说明图表类型。

**会话流**：方案卡片下方新增选项按钮组（主按钮“按此执行”、次按钮“更换方法”“解释依据”、幽灵按钮“自定义说明”与“补充对话”），点击后展开内联输入框；流式气泡左侧呼吸点 + 逐字文本，执行中显示步骤进度条。

**中断控制**：输入框右侧在生成/执行中变形为红色“中断”按钮；中断后出现“继续审阅”与“返回对话”两个操作。

**错误卡片**：浅红边框卡片，首行为错误码徽标（如 MISSING_PARAM），次行为可读说明与建议，详情默认折叠（pre 展示技术栈）。

## 交互与动效

选项按钮 hover 上浮 1px + 阴影扩散；能力抽屉滑入 220ms 缓动；流式文本光标闪烁；进度条分段点亮；中断按钮呼吸动效提示可终止。

## 响应式

窄屏下能力抽屉全屏、工作区折叠为底部抽屉，选项按钮组换行铺满。

### Skill

- **tdd**：按 RED-GREEN 垂直切片实现工具契约校验、错误分类、流式与中断路由、选项路由，行为列表驱动测试循环
- **agently-request**：规范 `ModelGateway.stream_text` 的流式契约与异常分类，确保结构化输出与增量文本共用同一请求语义
- **agently-triggerflow**：规范执行中 interrupt/resume 与 TriggerFlow 暂停审阅的语义边界，避免自研状态存储
- **agently-design**：核对工具目录注入、宿主校验与模型决策的所有权划分，保证单一真相源
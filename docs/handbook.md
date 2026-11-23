# MedSta 产品与实现讲解手册（教学版）

> **这份文档回答的问题**：MedSta 为什么这样设计、代码如何一步步跑起来、模型与宿主各自负责什么、
> 前端如何被事件驱动、以及「我要加一个功能」应该改哪里。
>
> **与其它文档的分工**：三张架构图只在 [系统架构与统计流程](./architecture.md) 维护（本文只链接、不复制）；
> 方法学口径见 [统计说明](./statistics-methods.md)；产品范围见 [产品说明](./product-guide.md)；
> 决策推理见 [设计决策](./design-notes.md)；本文负责**把三份文档之间的空隙教清楚**。
>
> **版本基线**：对齐 spec 048（2026-11-20）——含 047 统计工作流编排（流程图方案 / 节点级交付 /
> 断点续接 / 会话上下文 / 内置 skills）与 048 推荐流程 + AI 一键匹配。

**目录**：0 阅读路线 ｜ 1 心智模型 ｜ 2 架构全景 ｜ 3 后端实现 ｜ 4 Agent 编排 ｜
5 执行编排 ｜ 6 统计内核 ｜ 7 前端实现 ｜ 8 契约速查 ｜ 9 开发流程与质量门 ｜
10 动手实验 ｜ 11 排错手册 ｜ 12 代码地图 ｜ 13 延伸阅读

## 0. 阅读路线

| 你是 | 建议路线 | 预计 |
|---|---|---|
| 第一次接触项目 | 第 1 章 → 第 2 章 → 第 8 章契约速查 | 40 分钟 |
| 要改后端 / Agent | 第 3 → 4 → 5 → 6 章，然后第 10 章实验 L2/L3/L5/L9/L10 | 2 小时 |
| 要改前端 | 第 7 章 + 第 8 章，然后第 10 章实验 L6 | 1.5 小时 |
| 要排线上问题 | 第 11 章排错手册 + 第 12 章代码地图 | 按需 |
| 要评审设计 | 第 1.2 三条铁律 + 第 4.10 反模式清单 + 第 9 章质量门 | 40 分钟 |

读代码的顺序（新人最短路径）：

```text
后端：main.py → medsta/launcher.py → medsta/app.py → session/service.py::handle
      → _on_chat → agents/discussion.py → stats/registry.py → pipeline/executor.py
      → pipeline/workflow.py → agents/interpretation.py
前端：types.ts → App.tsx::handleEvent → chat/ChatPanel.tsx → chat/{Plan,Review,AnalysisConfig}Card.tsx
      → workspace/WorkspacePanel.tsx → builder/ChainBuilder.tsx
```

---

## 1. 十分钟建立心智模型

### 1.1 产品一句话

上传一张表 → 用自然语言说清分析目标 → 模型产出**结构化方案** → 用户确认（图表/α/校正）→
**确定性统计引擎**执行 → 交付统计表、图表、策略链与受控解读 → 可修正再执行。

### 1.2 三条铁律

这三条不是风格偏好，而是全部代码的组织原则。任何一个新功能如果违反其中一条，都会在评审中被打回。

**铁律一：模型只拥有语义决策，其余全部归宿主。**

| 归模型 | 归宿主 |
|---|---|
| 这段诉求想做什么统计（描述/比较/关联/预测） | 方法是否在注册表里、参数是否齐全、列是否存在 |
| 选哪个方法、对哪些列、为什么（rationale） | p 值、置信区间、显著性星号、样本量 |
| 把已给数值写成中文句子 | 数值白名单、因果断言拦截、句数截断 |
| 判断输入是否与统计任务无关（`off_topic`） | 明显闲聊的零 token 预筛 |

判断标准只有一句：**「这句话/这个数，模型说错了会不会造成不可复现的结论？」** 会，就必须归宿主。

**铁律二：状态归宿主，模型不决定流程。**

`discussing → plan_confirmed → executing → delivered`（修正回讨论）由 `session/manager.py`
的转移表强约束；前端的 `phase` 只是这份状态机的投影，不能反过来决定服务端路由。

**铁律三：同一个事实只有一个真相源。**

| 事实 | 唯一真相源 | 消费者 |
|---|---|---|
| 有哪些统计方法、要什么参数、能画什么图 | `stats/registry.py` 的 `_REGISTRY` | 模型目录注入、`/capabilities`、校验、执行派发、文档附录 A |
| 会话处于哪个阶段 | `SessionStatus` + `_ALLOWED_TRANSITIONS` | 全部 handler、前端 phase |
| 会话重建所需状态 | `SessionStore` 快照 | 启动恢复、`GET /sessions/{sid}/workspace` |
| 出站帧顺序 | `EventLog` 的单调 `seq` | WS 推送、`resume` 补发、回放 |
| 前后端消息形状 | `spec/done/006-session-api.md` + `frontend/src/types.ts` | 契约测试、前端渲染 |

### 1.3 两个模式、四个状态

```text
讨论态（模型主导语义，宿主校验）              执行态（宿主确定性执行，模型不参与）
chat → stream → plan ──confirm_plan──→ chart_config ──chart_choice──→ executing
  ↑                                                                        │
  │                                                                 review_request
  │                                                                        ↓
  └── back_to_discussion ←── review(revise) ←────────────────────── 审阅（等人）
                                                                           │
                                                                 review(accept)
                                                                           ↓
                                                          delivered（chat 走答疑；
                                                          再修正则回讨论）
```

四个状态的精确定义与允许转移见第 3.5 节；一次完整心跳见第 1.5 节。

### 1.4 术语表

| 术语 | 含义 | 代码位置 |
|---|---|---|
| 画像 / profile | 表的行数、列数、逐列类型与统计摘要 | `data/profiler.py::TableProfile` |
| 工作区 / dataset | 会话下的一个数据集（含画像、数据文件、产物目录） | `session/manager.py::SessionData` |
| 方案 / plan | 模型产出的结构化步骤数组 + 选项 + 估计目标 | `agents/discussion.py::AnalysisPlan` |
| 步骤 / step | 一次工具调用（方法 + 目标列 + 图表 + 参数 + 依据） | `PlanStep` |
| 报告 / report | 按方案逐步执行的结果集合 | `pipeline/executor.py::ExecutionReport` |
| 策略链 / strategy | 执行期「为什么最终用这个方法」的依据链 | `result["strategy"]` |
| 方法学说明 / method_note | 教材口径固定文案（非模型生成） | `stats/notes.py::METHOD_NOTES` |
| 证据包 / evidence | 解释用白名单数值集合（不含原始数据行） | `agents/interpretation.py::build_evidence` |
| 回放帧 / `*_user` | 用户动作写入事件流后补发的帧 | `session/service.py::USER_ACTION_EVENTS` |
| 流程图 / flow | `steps[].depends_on` 生成的节点图（nodes/edges/order/mermaid） | `agents/flow.py::plan_flow` |
| 节点交付 / step_result | 单个节点完成即下发的中间结果（失败也交付） | `pipeline/executor.py::execute_node` |
| 会话上下文 / context | 已确认工作流 + 节点状态 + 失败原因 + 用户补充 | `session/context.py::SessionContextStore` |
| 统计 skills | 方法学规则条目（决策树/误用/报告规范） | `agents/stats_skills.py::SKILLS` |
| 推荐流程 / recipe | 用占位槽位描述的内置工作链骨架 | `agents/chain_recipes.py::RECIPES` |

### 1.5 一次会话的完整心跳（跨前后端）

```text
 1  用户拖入 CSV                        useFileDrop → requestUpload
 2  前端 POST /sessions/{sid}/data      routes_data.upload_data（def → 线程池）
 3  解析 → 画像 → 挂载工作区             load_table → profile_dataframe → manager.attach_data
 4  返回 data_profile（type_confirmed=false） + 落快照
 5  用户点「敲定类型」                    WS type_confirm（或 PATCH .../columns 批量）
 6  宿主校验全部列 → 应用 → 落快照 → 广播 type_confirmed（含 updated/source）
 7  用户输入需求                          WS chat
 8  宿主预筛（零 token）→ 数据检查 → 模型配置检查 → 类型门控 → 忙锁
 9  后台任务 _generate_plan               progress(thinking) + 模型流式 stream(thinking)
10  输入组装：画像 + 工具目录 + skills    skills_for_request（关键词挑选，确定性）
11  模型返回 AnalysisPlan；缺 rationale    宿主自动发一轮「只补依据」请求（_ensure_rationales）
12  双层校验（pydantic + registry）        硬错误带反馈重试一次；仍失败 → INVALID_PLAN + issues
13  下发 plan（steps + flow + estimand）   前端渲染方案卡 + 工作流图（PlanFlowView）
14  用户点 confirm                        WS confirm_plan（或 option action=confirm）
15  有图步骤 → PLAN_CONFIRMED + chart_config（每步只列该工具支持的图）
    无图步骤 → 直接 _execute_plan
16  用户确认图表/画板/α/校正               WS chart_choice（非法值宿主降级）
17  宿主 EXECUTING → 创建 TriggerFlow 句柄 → 后台 _execution_task 启动
18  执行器逐节点 execute_node（to_thread）  progress(executing) + step_result（每节点交付）
19  节点失败 → 不阻断后续                   StepDeliveryCard 展示错误；执行期按钮置灰
20  TriggerFlow 进入审阅暂停点（pause_for）→ 返回完整 report
21  宿主落快照 → review_request → 注册 imputed/cleaned 数据集(dataset_added) → plot_suggest
22  解释后台任务（不阻塞）→ interpretation（失败静默）
23  节点补救（审阅态可用）                  retry_step（零模型）或 amend_step（模型只改该节点）
                                            → 重跑该节点及下游 → review_request{updated}
24  用户 accept → DELIVERED（落盘先于送达 → delivered）→ 可答疑；revise → 回讨论
```

把这张表记住，后面所有章节都是在展开其中某一步。第 18–19 步与第 23 步是 047 的核心增量：
**交付粒度从「一次执行」下降到「一个节点」**——失败不再等于整条链重来。

---

## 2. 架构全景

### 2.1 七层与职责边界

| 层 | 目录 | 职责 | 不该做什么 |
|---|---|---|---|
| 呈现层 | `frontend/src/` | 事件驱动的界面状态、上传、导出、装配 | 决定服务端路由、自己算统计 |
| 鉴权层 | `app.py` 中间件 + `api/ws.py` 握手 | 令牌 → 身份；归属隔离（404/4403） | 只保护 REST 忘了 WS |
| 传输层 | `api/routes_*.py`、`api/ws.py` | 请求解析、状态码、薄封装 | 写业务分支（逻辑在 service） |
| 编排层 | `session/` | 状态机、消息分发、后台任务、快照、事件流、模板 | 做统计、写提示词 |
| 语义层 | `agents/` | 方案 / 解读 / 答疑 / 列类型建议 | 计算数值、决定状态 |
| 执行层 | `pipeline/` + `stats/` | 校验、派发、计算、绘图、方法说明 | 调模型 |
| 数据层 | `data/`、`reporting.py` | 解析、画像、报告渲染 | 决定分析方案 |

依赖方向是单向的：`api → session → agents/pipeline → stats/data`。反向依赖只出现在
「执行层把结果交给 session 注册数据集」这种通过返回值完成的松耦合上。

### 2.2 状态放在哪里

| 状态 | 介质 | 生命周期 | 谁写 |
|---|---|---|---|
| 会话对象、`plan`、`reports`、忙锁、任务句柄 | 进程内存（`manager` 单例 + `SessionService` 字典） | 进程内 | service |
| 会话快照 `snapshot.json` | 磁盘，原子写 | 跨重启 | `SessionStore` |
| 出站事件 `events.jsonl` | 磁盘，追加写 + 阈值轮转 | 跨重启 | `EventLog` |
| 执行记录（报告 / 会话消息） | Agently `LocalRecordStore`（SQLite） | 长期 | `pipeline/workflow.py`、`service._record` |
| 数据集文件、图表产物 | `data/sessions/<sid>/<dsid>/` | 长期 | `routes_data`、`execute_step` |
| 工作链模板 | `data/sessions/templates/*.json` | 长期 | `session/templates.py` |
| 分析上下文（图 + 节点进度 + 失败原因 + 用户补充） | 进程内存（`SessionContextStore`，`owner → session` 分层） | 进程内（删除会话即释放） | `service._remember_plan/_mark_node` |
| 前端界面状态（消息 / phase / 交互卡 / 节点交付 / 工作区） | React state（按 sessionId 分桶） | 页面内 | `App.tsx` |

**为什么快照与事件流要分开**：快照回答「现在是什么」，事件流回答「发生过什么」。
刷新时先取快照补齐，再用回放做增量——只靠任何一方都会出现「左栏有、右栏空」或
「回放堆出重复报告」。这条决策的完整推理见 [design-notes.md §19](./design-notes.md)。

### 2.3 三条不可跨越的边界

1. **模型/宿主边界**：模型输出永远只是一个 `dict`，必须经过 pydantic（形状）与
   `registry.validate_step`（语义与数据）两道校验才能进入执行。
2. **前端/后端边界**：前端不推导统计结论、不判断状态机；服务端不依赖前端传来的 `phase`。
3. **测试/真实模型边界**：测试默认不触网、不读 `.env`（conftest 强制 `build_gateway` 抛错），
   真实模型只有一个显式入口 `tests/test_real_llm_smoke.py`。

---

## 3. 后端：从进程启动到一次事件处理

### 3.1 启动链

```text
python main.py
  → sys.path 注入 backend/src
  → medsta.launcher.main()
      dev  : uvicorn medsta.app:app --port 8000 + npm run dev -- --port 5173
      prod : npm run build → uvicorn（单端口托管 SPA + API）
  → uvicorn 首次取属性 medsta.app:app（PEP 562 __getattr__ 惰性构建）
      → create_app()
          → 读取鉴权环境变量（MEDSTA_USERS 优先于 MEDSTA_AUTH_TOKEN）
          → 注册 auth_guard 中间件
          → include_router × 7
          → app.state.data_root = root
          → app.state.service = _build_service(root)
              → LocalRecordStore(root.parent/"records")
              → build_gateway()：缺配置时 RuntimeError → 三个 agent 置 None（服务仍可启动）
          → service.restore_all()：从快照恢复历史会话
          → mount /data（静态产物）
          → 若 frontend/dist/index.html 存在 → 挂 /assets + catch-all SPA 回退
```

**教学点**：为什么模块级 `app` 要惰性构建？因为导入 `medsta.app` 的行为会触发
`restore_all()`（扫描真实数据根、加载 CSV、构建模型网关）。测试里只 import 一个函数就
产生副作用是不可接受的，所以用 `__getattr__` 在第一次取 `app` 时才构建并 memoize。
配套的机制是 conftest 的 autouse 夹具把默认数据根重定向到 tmp，并把 `build_gateway`
替换为抛错——「测试不写真实数据、不依赖 .env」由约定变成了机制。

**运行期排障的前置知识**：dev 模式的 uvicorn **没有 `--reload`**（启动期会做全量快照恢复），
代码更新后必须重启才生效；`launcher` 默认把子进程输出追加到 `logs/dev.log`
（5MB 轮转 `.1`），前端遇到「快照接口 404」会直接提示「代码已更新但服务未重启」。

### 3.2 会话对象模型

```python
Session(
  session_id, owner, status,
  datasets: dict[dataset_id, SessionData],   # 多工作区
  active_dataset_id,                          # 决定 chat 用哪张表
  plan, messages,
)
SessionData(df, dataset_path, profile, artifact_dir, name, type_confirmed)
```

- `session.data` 是 `active_dataset_id` 的取值器（没有激活项时回落到第一个数据集）。
- **每个数据集有独立的 `artifact_dir`**：图表按数据集隔离，避免插补表与原表产物互相覆盖。
- `type_confirmed` 是讨论的前置门控：未敲定类型时 `chat` 会被挂起并回 `type_review`，
  用户确认后自动继续那条被挂起的消息（`_pending_chats`）。

### 3.3 SessionService 的账本

`SessionService` 没有引入任何依赖注入框架，全部状态是 `session_id → 值` 的字典。
读源码前先把这张表记住，否则会在 2000 行里迷路。

| 字段 | 含义 | 典型写入点 | 清理点 |
|---|---|---|---|
| `_agent` / `_interpret_agent` / `_type_advisor` | 三个模型能力入口 | 构造 / setter | — |
| `_contexts` | 会话上下文（owner → session）：已确认工作流、节点状态、失败原因、用户补充 | `_remember_plan`、`_mark_node`、`amend_step` | `delete_session`（`drop_session`） |
| `_plans` | 当前方案（执行与解释要用） | `_generate_plan`、`_execute_plan` | `delete_session` |
| `_reports` | 当前报告（导出、补图、答疑要用） | `_execution_task`、`_on_plot_later` | `delete_session` |
| `_report_history` | `report_id → report`（历史导出寻址） | `_execution_task`、`restore_all` | `delete_session` |
| `_revision_notes` | 用户修正意见（注入下一次讨论） | `_on_review(revise)` | 执行时消费、删除会话 |
| `_pending_chats` | 等类型确认时挂起的消息 | `_on_chat` | 类型确认后消费 |
| `_requests` | 最近一次用户诉求（解释上下文） | `_generate_plan` | 删除会话 |
| `_busy` | 同会话忙锁（生成/答疑/装配执行） | `_on_chat`、`_answer`、`_on_run_chain` | `_release_task_slot`、interrupt、删除会话 |
| `_tasks` | 后台任务句柄（生成 / 答疑 / 执行驱动） | 各 create_task 点 | 身份匹配释放 |
| `_interpret_tasks` | 解释后台任务 | `_start_interpretation` | 新解释、中断、删除会话 |
| `_workflows` / `_executions` | TriggerFlow 工作流与执行句柄 | `_execute_plan` | accept/revise/interrupt/超时/删除 |
| `_senders` | 在线 WS 连接（REST 变更也能实时推送） | `ws.py` attach | 连接断开 detach |

**教学点：为什么 `_release_task_slot` 要比较 `asyncio.current_task()`？**
`interrupt` 的取消是异步投递的，旧任务可能在**新任务已经登记之后**才执行到 `finally`。
如果无条件 `pop` + `discard(busy)`，旧任务会把新任务的句柄和忙锁一起清掉——结果是
「中断失效」+「同会话双跑」。所以收尾必须确认槽位仍属于自己。

### 3.4 消息分发与错误统一

```python
handle(session_id, event, send)
  ├─ 会话不存在 → NO_ACTIVE_RUN
  ├─ 用户动作入事件流（<type>_user，占 seq、不实时广播）
  ├─ handler 表分发（chat/confirm_plan/review/interrupt/resume/option/workspace/
  │                    chart_choice/type_confirm/plot_later/run_chain/
  │                    retry_step/amend_step/suggest_column_types）
  ├─ 未知类型 → PROTOCOL_UNSUPPORTED
  └─ InvalidStateTransition → PROTOCOL_UNSUPPORTED（协议顺序错误，客户端可见）
```

三条纪律：

1. **任何失败都要变成带 `code/message/hint/detail` 的事件**，不允许静默 500 或直接断连。
2. **协议错误与业务错误分开**：未知消息 ≠ 方案要改（后者才是 `INVALID_PLAN`）。
3. **状态转移失败不崩溃**：`manager.transition` 抛 `InvalidStateTransition`，由 `handle` 统一转帧。

### 3.5 状态机

```python
_ALLOWED_TRANSITIONS = {
    DISCUSSING:      {DISCUSSING, PLAN_CONFIRMED, EXECUTING},
    PLAN_CONFIRMED:  {EXECUTING, DISCUSSING},
    EXECUTING:       {DELIVERED, DISCUSSING},
    DELIVERED:       {DISCUSSING, DELIVERED},
}
```

- 转移表是**强约束**，不是注释：`PLAN_CONFIRMED` 期重复 `confirm_plan` 会被拒绝（否则重复下发 `chart_config`）；
  `DELIVERED` 期 `confirm_plan` 也不会用残留 `plan` 重跑旧方案。
- **恢复期是特例**：`restore_all` 与「恢复的审阅态直接交付」属于状态重建，
  直接赋值而不走转移表；这样转移表本身可以保持严格（`discussing` 永远不能直接跳 `delivered`）。
- `executing` 跨重启一律降级为 `discussing`——没有句柄的执行不可能继续，留着只会让用户卡死。

### 3.6 持久化双通道

**快照 `snapshot.json`（只存重建所需最小状态）**

```json
{
  "version": 1, "session_id": "...", "owner": "local", "status": "discussing",
  "active_dataset_id": "ab12cd34",
  "datasets": [{"id","name","path","type_confirmed","column_types"}],
  "plan": {...}, "report": {...}, "updated_at": "..."
}
```

- 不序列化 DataFrame：重启时用 `load_table(path)` 重新加载，快照体积可控。
- 原子写（tmp + `os.replace`），失败返回 False 并降级内存模式，不阻塞主流程。
- 恢复时逐列重放用户敲定的列类型（非法值跳过），避免「改了类型，重启后又变回去」。

**事件流 `events.jsonl`（只追加）**

- `commit(session_id, message)`：分配 `seq = max+1` → 落盘 → 返回完整帧；
  落盘失败只降级投递（回放完整性受损，但不阻塞实时会话）。
- 计数器惰性恢复：首次访问从文件读最大 seq，重启后续接不回退。
- 超过 `EVENT_LOG_MAX_LINES`（2000）原子轮转，保留尾部一半——崩溃不会截断整份日志。

**为什么要两个通道**：快照保证「刷新后右栏与左栏同源」，事件流保证「聊天上下文可完整回放
（含用户动作帧）」。两者按 `dataset_id` / `report_id` 幂等合并。

### 3.7 WebSocket 端点

`api/ws.py` 是薄封装，只做四件事：

1. **握手鉴权**：多用户模式校验 `token → username` 与会话归属（失败 close `4403`）；
   单令牌模式校验 `?token=`（失败 close `4401`）。WebSocket 不经过 HTTP 中间件，必须自校验。
2. **出站加锁**：`send` 与 `send_frame` 共用 `asyncio.Lock`——进度回调（`ensure_future`）
   与主流程可能并发写帧。
3. **注入 seq**：每帧 `EventLog.commit` 后发送；REST 触发的变更经 `service.broadcast` 复用同一通道。
4. **resume 补发**：`{"type":"resume","last_seq":N}` 时先原样补发 `seq > N` 的历史帧（绕过分配）。

循环内三类异常都不会断连：JSON 解析失败 → `INVALID_PARAM` 帧并 `continue`；
service 抛出 `AppError` → 错误帧；其它异常 → `EXECUTION_FAILED` 帧。

### 3.8 鉴权三态

| 配置 | 行为 | 前端表现 |
|---|---|---|
| 都没配 | 直通，`owner="local"`，零开销 | 匿名工作台 |
| `MEDSTA_AUTH_TOKEN` | 单令牌；`X-Auth-Token` / `Authorization: Bearer` / `?token=` | 令牌存 localStorage |
| `MEDSTA_USERS=user:pass,...` | `/auth/login` 换内存令牌；按 owner 隔离 | 401 → 登录卡 |

细节（都是踩过的坑）：

- **静态外壳必须放行**：`/`、`/index.html`、`/assets/*`、`/favicon.ico` 若也要令牌，
  prod 单端口 + 鉴权会整页 401 白屏——浏览器连登录页和脚本都加载不了。
- **归属隔离用 404 不用 403**：不泄露「这个会话存在但不属于你」。
- **集合级动作要白名单**：`POST /sessions/cleanup_duplicates` 作用于本人全部会话，
  没有单会话可查，必须跳过按 `session_id` 的归属判定，否则永远 404。
- **login 加固**：`secrets.compare_digest` 常数时间比较（未知用户用空串占位保持耗时一致）
  + 同 IP 60 秒窗口 5 次失败 → 429，成功清零。内存计数，单进程适用。
- **WS 4401/4403 不重连**：令牌在服务端内存表里，后端重启后全部失效；
  前端收到这两个码应停止退避并回登录卡。

### 3.9 并发、中断与超时

**执行为什么拆成 `create` + `start`**

| 阶段 | 行为 | 原因 |
|---|---|---|
| `workflow.create(...)` | 同步创建执行句柄（`auto_close=False`），登记资源 | 句柄在启动前就能被 interrupt/清理拿到 |
| `workflow.start(execution)` | 内部 `async_start`，阻塞到 TriggerFlow 第一个暂停点 | 若直接在 handler 里 await，计算期间 WS 收包完全阻塞，中断名存实亡 |
| `_execution_task` | 后台任务驱动 start → wait_for_review → 下发 | 收包循环保持可用 |
| `workflow.cancel` | `async_close(pending_interrupts="cancel")` | **会 drain 计算线程**，只能在后台任务里等 |

中断路径的完整语义：

```text
interrupt
  ├─ 取消解释任务、丢弃忙锁
  ├─ 立即弹出 _executions/_workflows（保证状态一致，避免残留句柄被 accept 交付）
  ├─ 若后台任务已自然结束（审阅等待期）→ 就地 await cancel
  ├─ 取消后台任务 → 被取消任务的 CancelledError 路径里 await workflow.cancel
  └─ 非 DELIVERED → transition(DISCUSSING) → 推 interrupted（单一响应方，不重复发帧）
```

超时分两层：执行阶段 600s 兜底（`_EXECUTION_TIMEOUT`），审阅等待 10s（`_REVIEW_TIMEOUT`）。
不能用一个超时同时约束两者——大计算量会被误判为「审阅超时」，或者审阅等待被无限拉长。

### 3.10 会话上下文与断点续接（047）

为什么需要 `SessionContextStore`：模型每次只能看到「画像 + 本轮诉求」。节点报错后用户补充一句
「按性别分层、别用方差分析」，如果模型不知道「已确认的图长什么样、哪几个节点已完成、哪个失败、
为什么失败」，它只能重新出方案——这就是「一次报错全部重来」的另一半根因。

```python
SessionContext(
  dataset_id/name/row_count/column_count,   # 数据摘要
  nodes,                                    # 来自 plan_flow(plan)，与 UI 同源
  node_states: {index: pending|running|done|failed},
  node_errors: {index: {code,message,hint}},
  notes: [用户补充]（上限 5 条）,
  turns: [最近诉求]（上限 5 条，单条 200 字）,
)
snapshot(limit=2000) → 给模型的最小文本（图与进度优先，剩余预算放最新补充）
```

三条设计约束：

1. **分层存**：`owner → session_id → SessionContext`。单用户时 owner 为 `local`；
   多用户上线后无需改调用方即可隔离（`get(session_id, owner)`）。
2. **生命周期跟随会话**：`delete_session` 调 `drop_session`；没有这个清理就是内存泄漏
   （与 `_plans`/`_reports` 同类问题）。
3. **只放可安全注入模型的事实**：数据摘要、节点参数、失败原因、用户补充；**不放原始数据行**。

写入点只有三个：`_remember_plan`（方案生成或手动装配时）、`_mark_node`（节点完成/失败时）、
`amend_step` 前（用户补充）。`snapshot()` 是唯一读取出口，保证 prompt 体积可控。

### 3.11 推荐流程模板匹配（048）

```text
GET /templates/builtin                 → recipe_catalog()（内置 5 条骨架，只读）
POST /sessions/{sid}/chain/match       → service.match_chain_recipe(session_id, recipe_id, use_ai)
    ├─ candidates_for(df, profile, slot)    # 宿主按类型/组数/取值确定性筛候选
    ├─ ChainMatchAgent.match(...)           # 模型只在候选内挑列（一次结构化请求，失败即回退）
    ├─ match_recipe(recipe, df, profile, choices)  # 复核：候选外选择被忽略，改用规则候选
    └─ 逐步 validate_step(硬错误)           # 组合后才暴露的约束（如 chi_square 缺列）→ 移除 + warning
```

边界：**候选集归宿主，语义选择归模型，最终合法性归 `validate_step`**。
模型不可用、请求失败、返回候选外列，都不会让「载入模板」变成不可用——最多退化为规则匹配，
并在 `matched[].by` 里标注来源。返回的 `steps` 直接进装配区，用户仍可编辑后 `run_chain`。

---

## 4. Agent 侧：模型只做语义决策

### 4.1 Owner 判据：三个问题

设计一个新模型能力时，先回答：

1. **这个输出会被谁消费？** 没有消费者的字段不允许出现在 `.output` 里。
2. **说错了会不会不可复现？** 会 → 宿主校验/计算，模型只提供候选。
3. **它是语义判断还是规则判定？** 语义（意图、方法适配、文案）归模型；
   枚举、边界、算术、状态、副作用归宿主。

### 4.2 ModelRequest：一次交互的四段式

`config.ModelGateway` 是全项目唯一的模型调用入口：

```python
request_structured(schema, fields=..., input=..., info=..., instruct=...)
  → request.input(input)      # 运行时事实：用户这句话
  → request.info(info)        # 权威资料：画像、工具目录、证据包
  → request.instruct(instruct)# 规则：怎么想、不能做什么
  → request.output(fields, format="json")
  → raw = request.start()
  → schema.model_validate(raw)   # 宿主 pydantic 是最终权威
```

四条契约：

- **消费字段全部在 `fields` 里声明**，模型不得产出契约外字段；
- `fields` 只描述形状，**语义约束仍由宿主代码兜底**（例如目标列必须在画像里）；
- 传输异常统一分类为 `MODEL_REQUEST_FAILED`，`detail` 截断 300 字，不泄漏密钥；
- `request_factory` 是**唯一的测试接缝**——在传输边界注入假实现，不 mock 业务函数。

流式版本 `request_structured_stream` 多做了两件事：

1. 遍历 `result.get_async_generator(type="original")`，从 SSE chunk 里取增量文本
   （优先 `reasoning_content`，兼容端可能给 `null`）；
2. 流结束后 `await result.async_get_data()` 再校验成 schema——**流式只影响展示，不影响契约**。

> 配置坑：`build_settings` 必须逐键点路径 `set_settings("plugins.ModelRequester.OpenAICompatible.xxx", v)`。
> 直接传 settings model 会整体替换插件命名空间，丢掉 `path_mapping` / `content_mapping` 默认值。

### 4.3 DiscussionAgent：方案是怎么长出来的

**输入组装**（每次讨论固定三块）：

```text
input  : 用户原话（含修正意见时由 instruct 追加）
info   : 1) TableProfile 全量 JSON（行数/列数/逐列类型与七列统计）
         2) 列类型摘要（continuous/ordinal/categorical/index）
         3) tool_catalog() 的 JSON（方法/参数/group_param/适用条件/可画图）
         4) skills_for_request(诉求) 的方法学要点（关键词挑选，≤1400 字）
instruct: 九条链条 —— 定性任务 → 明确槽位（类别列只进分组参数）→ 选方法 →
          预告前提与降级 → 写 rationale → 显著性规范 → 2–4 个选项且必须含 confirm →
          估计目标五要素；另要求 steps[].depends_on 声明依赖（可选）
output : message / steps(title,method,target_columns,chart_type,params,rationale,depends_on)
         / options / off_topic / off_topic_reason / estimand
```

**宿主的三道收口**：

1. `AnalysisPlan.model_validate`：`method` 与 `chart_type` 是 `Literal` 枚举，
   不在注册表里的方法在这一步就会被拒（`MethodType` 必须等于注册表键 ∪ `ALIASES`，
   由 `tests/test_method_contract.py` 守护）。
2. `validate_plan`：工具存在、列存在、必填参数、取值合法、图表属于该工具、数据充分。
   **只有 6 个硬错误码会拒绝执行**（`TOOL_NOT_FOUND` / `COLUMN_NOT_FOUND` / `MISSING_PARAM` /
   `INVALID_PARAM` / `INSUFFICIENT_DATA` / `COLUMN_TYPE_MISMATCH`）；
   `ORDINAL_HINT` 是软提示，会随方案一起展示但不阻断。
   类别列被放进 `target_columns` 时，hint 不再是泛泛的「可用 chi_square」，而是可执行修法：
   「target_columns 只放数值列，并在 `params.group_column` 里选它」。
3. `_assign_step_ids` + `_normalize_options`：宿主保证每步有唯一 `step_id`、
   选项 id 唯一、必须有 `confirm`、最多 4 个——这些是前端契约，不能让模型碰运气。

**「缺依据」不再直接判死（rationale repair）**：`rationale` 是硬门（没有依据的方案不可解释），
但模型偶尔整份漏填，用户会看到 6 条 `MISSING_PARAM` 却无从修改。现在 `_ensure_rationales`
在硬校验前补一轮「原样返回同样步骤、只补 rationale」的请求，宿主**只合并 rationale**，
method/targets/params 一律不动；补完仍缺才按硬门拒绝。补全失败保守返回原方案，
原有错误照常暴露——可解释性不降级，可用性提高。

**失败重试只做一次**：`_generate_plan` 捕获 `ToolValidationError`，把前 5 条 issue 拼成
「上一次方案被拒绝：…请修正后重新输出完整方案」追加进 instruct 再试一次；
仍失败则下发 `INVALID_PLAN` + 完整 issues（前端 ErrorCard 逐条渲染「步骤 + 原因 + 修法」）。
这不是通用重试管理器——它只处理「模型可在自身能力内修正的契约错误」。

**`depends_on` 的降级策略**：模型可以只给线性步骤，宿主 `flow._coerce_deps` 会补
`depends_on=[index-1]`；只接受更早节点的依赖（自环/反向/越界一律忽略），因此图始终可执行。

### 4.4 输入守卫：两层，语义仍归模型

| 层 | 归属 | 判定 | 成本 |
|---|---|---|---|
| 第一层 | 宿主正则 `_looks_like_chitchat` | 纯问候/致谢/告别/单字符（`你好`、`谢谢`、`ok`） | 零 token |
| 第二层 | 模型同请求自检 `off_topic` | 「这段输入与统计分析无关吗」 | 已含在一次方案生成里，不额外调用 |

命中后的行为：讨论态推 `chat_rejected`（notice 气泡引导描述统计需求、`phase` 重置 idle）；
答疑态替换为范围提示（不烧正式回答）。**这里没有用关键词判断「是不是统计问题」**——
只在第一层拦截明显闲聊，语义判断交给模型。

### 4.5 ColumnTypeAdvisor：建议，不是决定

```text
宿主组装证据（白名单，不传全量数据）
  每列：name / inferred_type / missing / distinct / sample_values(前 5 个唯一值) / stats
  → asyncio.to_thread(advisor.advise, evidence)      # 阻塞 HTTP，必须离开事件循环
  → 模型返回 columns[{name, suggested_type, confidence, reason}]
  → 宿主过滤非法类型 → 合法项下发 column_type_suggestions，非法项进 skipped
  → 用户「采纳」→ PATCH .../columns（批量、原子）→ type_confirmed
```

模型只有建议权：非法建议直接丢弃，用户保留最终敲定权。
这也是「语义建议 + 宿主校验 + 人类决策」三权分立的样板。

### 4.6 InterpretationAgent：证据工程

这是全项目最值得逐行读的 Agent 代码，因为它示范了如何让模型「只写句子」。

**第一步：把报告压成证据包（`build_evidence`）**

```python
{
  "profile": {"rows":…, "columns":…, "types": {...}},      # 画像摘要，不含数据行
  "estimand": {...} | None,
  "sap_status": "estimand_declared" | "exploratory",
  "steps": [{
      "ref": "S1", "title", "method", "target_columns", "rationale", "params",
      "values": _extract_values(method, result),            # 按方法白名单取键
      "method_note": ..., "warning": ..., "error": {...}
  }]
}
```

白名单长这样（`_SIMPLE_KEYS`）：`group_compare` 只放
`test/statistic/p_value/mean_diff/ci95/cohens_d/groups`；`chi_square` 只放
`chi2/dof/p_value/cramers_v/odds_ratio`；`descriptive_stats` 单独走
`n/mean/sd/cv/median/iqr/geometric_mean/recommended`。
**未列出的键（原始行、整张表、矩阵）一律不进 prompt**——prompt 体积恒定在 1–2k tokens，
同时消除「模型自己算数」的机会。

**第二步：三道宿主守卫（按严重度分层）**

| 守卫 | 类型 | 行为 | 为什么 |
|---|---|---|---|
| 因果断言 `_causal_violation` | **硬门** | 命中即整段不展示，重试一次仍违规则放弃 | 「治疗组导致改善」会被当成临床结论 |
| 未核验数值 `_unverified_numbers` | **软标** | 只标记角标，不拒绝 | 四舍五入（0.0287→0.03）是合法改写 |
| 句数超限 `_truncate_sentences` | **截断** | 按 `[。！？]` 取前 N 句 | 提示词只是提高服从率，真正生效靠宿主 |

因果守卫的模式是「因素/干预/治疗/用药/分组/暴露/变量/指标 + 0–12 字 + 导致/引起/造成/
使得/决定/证明/致使/带来」，并对匹配串及前 12 字内的否定词（不能/无法/不足以/并不/未/
不应/不可/不代表/不等于）豁免——这样「不能说明存在因果关系」这类正确表述可以保留。
它是**合规红线**，不是「用正则判断模型在想什么」。

数值软标放行三类：证据里出现过的数（允许 0–3 位四舍五入）、统计语篇常见数
（0/1/2/3/4/5/10/95/99/100）、`p<0.001` 形式。

**第三步：caveat 二选一**

`EXPLORATORY_CAVEAT` 与 `ESTIMAND_DECLARED_CAVEAT` 互斥，`_sanitize` 先剔除两条固定文案
再按 `sap_status_of(plan)` 追加一条。两条并列会互相稀释，用户读不出区别。

### 4.7 一次解读的完整链路（含防串台）

```text
_execution_task
  ├─ send review_request（用户先看到结果，不被解读阻塞）
  ├─ _register_imputed_datasets（impute/清洗产物 → dataset_added，不切 active）
  └─ _start_interpretation
        ├─ 记录报告指纹 signature = ((method, title), ...)
        ├─ 取消上一轮解释任务（同会话只保留最新）
        └─ asyncio.create_task(_interpret)
              ├─ await asyncio.to_thread(agent.interpret, ...)   # 阻塞 HTTP
              ├─ 异常 → 静默 return（增强项失败不影响交付）
              ├─ 校验 signature：报告已被新执行覆盖则丢弃（防串台）
              └─ send {"type":"interpretation", ...} + RecordStore 记录
```

交付态答疑走另一条链 `_answer → _answer_task`：只解释已交付报告，不产新方案；
忙判定在任何进度帧之前（否则会出现「正在回答…」紧接着 SESSION_BUSY 的自相矛盾）；
`finally` 必须释放忙锁，否则答疑失败一次会话就永久 SESSION_BUSY。

### 4.8 定点修正：只重写一个节点（`amend_step`）

「整份方案重来」在复杂工作流里代价太高（用户已确认的图、已完成的节点都作废）。
`DiscussionAgent.amend_step` 把修正范围压缩到一个节点：

```text
info = 画像 + 列类型 + 工具目录
     + plan_flow(plan)["nodes"]          # 当前整张图（让模型知道节点位置与邻居）
     + 待修正节点（序号 i+1）+ 该节点失败信息
     + SessionContext.snapshot()         # 已完成/失败/用户补充
     + 针对该节点挑选的 skills
instruct += 「steps 只输出 1 个元素，不得增删其它节点或改变其位置」
→ 宿主 validate_plan(单节点) 通过后，原地替换并保留 depends_on / step_id
→ _rerun_from(index) 重跑该节点及其下游；失败节点不阻断后续
```

四条不变量：

1. **模型不能改图结构**：只返回 1 个 step，依赖与 `step_id` 由宿主保留；
2. **校验不降级**：单节点仍走 `validate_plan` 硬门；
3. **失败不留残影**：模型/校验失败时不修改现有方案，只回错误；
4. **上下文可解释**：失败原因与用户补充都进 prompt，避免模型猜「为什么失败」。

与 `retry_step` 的分工：`amend_step` 是**模型改写节点**（一次结构化请求），
`retry_step` 是**用户改参数**（零模型）。两条路径都只作用于「该节点及下游」，
前序节点的结果原样保留。

### 4.9 统计 skills 的归属：宿主挑选，模型遵守

`agents/stats_skills.py` 的 `StatsSkill` 是「方法学规则条目」：
`when / rules / pitfalls / reporting / keywords`，覆盖两组比较、多组、分类、配对、回归、
生存、缺失、样本量、多重比较、SAMPL 报告规范。

关键边界：

- **挑选是确定性的**：`select_skills(text)` 按关键词命中数与顺序打分，最多取 4 条；
  未命中时给「报告规范 + 缺失数据」两条通用约束。这不是「用关键词判断统计语义」，
  而是**在已确定的诉求上控制注入哪几条规则**——统计语义仍由模型在工具目录内判断。
- **注入有预算**：`skills_digest` 截断到 1400 字，避免挤占画像与工具目录。
- **规则不越权**：skills 里写「Dunnett 需指定对照组」只是提示；真正的拦截在
  `validate_step` 的必填参数与运行期校验。

skills 与推荐流程的关系是「同一套方法学来源，各自消费」：skills 只注入讨论/修正 prompt；
`Recipe.skill` 在 `recipe_catalog()` 里作为来源标注对外披露，**不参与** prompt 注入——
避免同一批规则在两条链路上重复出现、互相稀释。

### 4.10 反模式清单（评审时逐条对照）

| 反模式 | 为什么禁止 | 本项目的正确做法 |
|---|---|---|
| 自定义状态存储 / 重试管理器 | 与框架 owner 重复、语义漂移 | `SessionStatus` + `SessionStore` + `EventLog`；重试只在具体调用点一次性 |
| 关键词/正则做语义判断 | 覆盖不全、无法解释 | 只做「明显闲聊」预筛与 skills 规则挑选，语义交 `off_topic` / 模型 |
| 未经消费的输出字段 | 白烧 token、契约虚胖 | `fields` 只列前端/宿主真正使用的字段 |
| 全量数据塞 prompt | 上下文膨胀、泄漏风险 | 只传 `TableProfile` 摘要、证据白名单、`SessionContext.snapshot()` |
| 让模型产出可执行代码 | 不可复现、不可测试 | 模型只选注册表里的方法与参数 |
| 把「提示」包装成「判定」 | 用户会误以为已识别 | 缺失机制只给 `mechanism_hint`，固定声明「不能仅凭数据断定」 |
| 让模型决定图结构 | 环/越界/不可执行 | `depends_on` 只允许更早节点，宿主补线性链并生成拓扑序 |

---

## 5. 执行编排：TriggerFlow + 注册表

### 5.1 为什么需要工作流而不是顺序函数调用

因为「执行完要**停下来等人**」，且「人可能不交付而是要求修正」。
这是应用层编排（开发者拥有），不是模型决策，也不是一次函数调用能表达的：

- 暂停/恢复（`async_pause_for` / `async_continue_with`）；
- 修正回边（`flow.when("RE_EXECUTE")`）在图上可见，而不是藏在 while 循环里；
- 执行在 `to_thread` 里跑，进度回调经 `call_soon_threadsafe` 回到事件循环；
- 交付时把报告写入 `LocalRecordStore`（可查询、可回溯）。

三张图见 [architecture.md](./architecture.md)（本文不复制图源）。

### 5.2 图定义（`pipeline/workflow.py`）

```python
flow.to(execute).to(review).to(route)
flow.when("RE_EXECUTE").to(execute)

execute(data):
    payload = data.resume if data.is_resume else data.input
    plan = AnalysisPlan.model_validate(payload["plan"])
    df = data.require_resource("dataframe")
    # 两个回调都经 call_soon_threadsafe 回到事件循环线程
    report = await asyncio.to_thread(executor.execute, df, plan, artifact_dir,
                                     on_step=…, on_step_result=…)
    await data.async_set_state("report", dump)
review(data):
    decision = await data.async_pause_for(type="plan_review", payload={"report": data.input},
                                          resume_to="next")
route(data):
    if decision == revise and decision.plan: emit("RE_EXECUTE")
    else: set_state("delivered", True); record_store.put(... collection="executions")
```

**教学点**：`RE_EXECUTE` 目前是一条「图可见但生产未接线」的回边——产品语义选择是
「revise → cancel → 回讨论重新出方案」，因此服务端从不发送带 `plan` 的 revise。
这条边保留在图上是为了表达编排能力，TO_DO 里把它列为待决策项（接线或移除）。

### 5.3 句柄时序（服务端视角）

| 调用方 | 动作 | 关键约束 |
|---|---|---|
| `_execute_plan` | `transition(EXECUTING)` → `create()` → 登记 → `create_task(_execution_task)` | 创建必须同步，否则中断拿不到句柄 |
| `_execution_task` | `await start()` → `await wait_for_review()` | start 阻塞到第一个暂停点（计算已完成） |
| `_on_review(accept)` | `workflow.review(execution, {"decision":"accept"})` | 内部 `async_continue_with` + `async_close` |
| `_on_review(revise)` | `workflow.cancel(...)` → 弹句柄 → 回讨论 | 修正意见存 `_revision_notes`，下次讨论注入 |
| `_on_interrupt` | 弹句柄 → 取消任务 → 后台 `cancel` | 不在收包循环里等 `async_close` |
| `_on_retry_step` | `validate_plan` → `_rerun_from(index)` | 零模型；只重跑该节点及下游，需无任务在跑 |
| `_on_amend_step` | `to_thread(agent.amend_step)` → 替换单节点 → `_rerun_from` | 保留 `depends_on`/`step_id`；失败不改原方案 |
| 超时 / 异常 | `_teardown_workflow` → 回 `DISCUSSING` → 错误帧 | 统一收口，不留可被交付的残留执行 |

`wait_for_review` 的实现是轮询 `execution.get_pending_interrupts()`（50ms 间隔），
但它先用 `asyncio.wait_for(self._exec_done.wait(), timeout=600)` 等计算完成——
这样「计算慢」和「审阅没人点」不会互相误伤。

### 5.4 执行器：确定性派发

```text
PipelineExecutor.execute(df, plan, artifact_dir, on_step, on_step_result)
  1) validate_plan → 有硬错误直接抛 ToolValidationError（整份计划拒绝）
  2) 逐步：
       on_step(index, total, title)                      # 进度帧
       execute_step_with_frame(df, step, artifact_dir, i)
         → get_tool → normalize_params（补默认值、choice 归一化）
         → handler(df, step, params)                     # 纯同步统计
         → result.setdefault("method_note", METHOD_NOTES[name])
         → chart_type != none → render_chart（失败记 chart_error，统计结果保留）
         → 剥离内部键 _next_frame
       next_frame 覆盖 df（链间管道：impute/清洗产物供后续步骤使用）
       单步异常 → StepResult(status="failed", error={code,message,hint})，继续下一步
       emit_step_result(index)                            # 节点级交付（成功/失败都发）
  3) 共享画板：_layout == "shared" 的图 ≥2 张 → render_combined 覆盖各步 artifact
        → 对该批节点再发一次 step_result(updated=True)
```

`execute_node(df, step, artifact_dir, index) -> (payload, next_frame)` 是单节点版本，
被 `_rerun_from` 复用。它**不外抛失败**，而是返回 `status=failed` 的 payload——
这样「重跑一个失败节点」与「首次执行到该节点失败」走同一条交付/展示路径。

**为什么单步失败要隔离**：一份计划里第 3 步失败，前两步的结果仍然有价值；
整份报告变成 error 会让用户无法判断「哪一步出了问题」。

**为什么出口要 `_jsonify`**：`numpy` 标量、`NaN/Inf`、`NaT` 都不是合法 JSON。
只要有一个漏转，`websocket.send_json` 就抛 `TypeError`，整帧 `review_request` 发不出去，
前端永远停在「执行中」。`np.bool_` 不是 Python `bool` 的子类，必须显式处理。

### 5.5 执行记录

`route` 节点在交付时把 `ExecutionReport` 写入 `LocalRecordStore`：

```python
put(json.dumps(report), collection="executions", kind="execution_report",
    summary=f"session {session_id} execution report", scope={"session_id": session_id})
```

会话级消息（用户诉求、解读、交付、答疑）另走 `service._record` 写 `collection="sessions"`。
查询按 `scope.session_id` 过滤——这是「记录归属」而不是「额外状态存储」。
`_record` 已旁路化：写入失败（SQLite 锁、事件循环切换）只记 warning，不把正常讨论变成
`EXECUTION_FAILED`——审计记录是增强项，不是主流程的成败条件。

### 5.6 节点级交付与断点续接（047）

**执行顺序的真相**：`steps` 的数组顺序就是执行顺序；`depends_on` 只允许指向更早的节点，
`plan_flow` 的 `order` 是拓扑序校验与展示用途，**执行器不会为了图并行化重排**。
这样「图」是用户可确认的依赖说明，而不是隐藏的调度器——简单、可预测、与报告顺序一致。

**节点级交付帧**

```json
{"type":"step_result","stage":"executing","index":2,"total":5,
 "step":{"index":2,"total":5,"updated":false,"title":"…","method":"anova",
         "status":"failed","error":{"code":"EXECUTION_FAILED","message":"…","hint":"…"}}}
```

服务端 `_step_result_sender` 同时把节点状态写进 `SessionContext`（done/failed + 错误），
因此后续 `amend_step` 的 prompt 里能出现「✓ [1] … / ✗ [3] … 失败原因」。

**两条恢复路径**

| 路径 | 谁改参数 | 是否调模型 | 作用范围 |
|---|---|---|---|
| `retry_step {index, overrides?}` | 用户（可选覆盖 params/target_columns/chart_type） | 否 | 该节点及下游 |
| `amend_step {index, note}` | 模型（只重写该节点） | 是（一次结构化请求） | 该节点及下游 |

共同约束：

- **忙锁串行**：有任务在跑时返回 `SESSION_BUSY`，重跑期间同样持锁；
- **先校验再执行**：`validate_plan` 硬错误 → `INVALID_PLAN` + issues，不进入循环；
- **不改变状态机**：重跑不重新走 `EXECUTING → DELIVERED`，直接更新已有 `report`
  并推 `review_request{updated:true}`（前端合并同一 `report_id`）；
- **失败不阻断**：`_rerun_from` 遇到失败节点继续下一个，与首次执行同语义；
- **交付边界**：`plan` 事件（amend 后）会清空前端上一轮节点交付，随后新 `step_result`
  重新填充——避免两次执行的结果混在一起。

**重跑与首次执行使用同一张表（2026-11-21）**

`_rerun_from` 与补图 `_on_plot_later` 在跑目标节点之前，先经 `_input_frame` 重放
`start` 之前的数据产出型节点（`FRAME_METHODS`：`impute` / 去重 / 筛选 / 标准化 / 分箱 / 截尾）。
非产出型节点不重算，避免改写已经交付的统计图。插补使用固定随机种子，重放与首次执行是同一张表。
每个重跑节点的结果同时 `_mark_node`，成功会清掉上下文里旧的失败原因，下一次 `amend_step`
读到的是当前状态。

---

## 6. 统计内核（教学向）

### 6.1 注册表是最重要的数据结构

`ToolSpec` 一张表描述了工具的全部对外事实：

```python
ToolSpec(
  name, title, category, description,
  params: tuple[ToolParam, ...],     # column/column_list/choice/integer/boolean/string/number
  charts: tuple[str, ...],           # 允许的图表（前端下拉的白名单来源）
  handler,                            # 纯函数 (df, step, params) -> dict
  min_rows, group_param, accepts,     # 数据充分性与列类型约束
  task,                               # 描述/关联/因果/预测/决策
  applicability,                      # 适用条件（进模型上下文）
  slots,                              # 语义槽位：group_col/value_col/agg…
)
```

新增一个统计方法时，**核心改动只有注册表 + 实现 + 方法说明三处**（外加 `MethodType`
枚举名，否则 pydantic 会先一步拒绝模型输出），模型目录、前端下拉、`/capabilities`、校验、
执行派发会自动跟上。但有三处文档守护会拦漏改：

- `tests/test_method_contract.py`：`MethodType` / `ChartType` 必须与注册表一致；
- `tests/test_docs_consistency.py`：架构附录 A、`docs/tools.md`、产品说明必须覆盖且不多不少；
- `tests/test_json_contract.py`：每个工具的输出必须可严格 JSON 序列化（`allow_nan=False`）。

`tool_catalog()` 现在还下发 `group_param`：装配器据此知道「这个工具的分组参数叫什么」，
在用户把类别列勾进目标列时实时提示，并提供「一键设为分组列」。这是「注册表作为单一真相源」
再次兑现——前端不需要维护一张方法到分组参数名的映射表。

### 6.2 校验顺序（`validate_step`）

```text
1  工具存在？                       → TOOL_NOT_FOUND（直接返回）
2  rationale 非空？                 → MISSING_PARAM
3  逐列类型：index 拒 / ordinal 软提示 / 与 accepts 不匹配 → COLUMN_TYPE_MISMATCH
   （类别列 + 工具声明了 group_param 时，hint 给出可执行修法：移出 target、填进分组参数）
4  逐列存在？                       → COLUMN_NOT_FOUND
5  至少一个目标列？（设计期与清洗工具豁免） → INVALID_PARAM
6  图表属于该工具？                 → INVALID_PARAM
7  参数：必填 / column 存在 / column_list 非空且存在 / choice 合法 / integer 合法
8  有硬错误 → 立即返回（软提示不再继续）
9  chi_square 的两列来源（target_columns 或 row_column/col_column）
10 数据充分性（_check_data）：分组 ≥2 组、group_compare ≤2 组、有效数值 ≥ min_rows、
   列联表每变量 ≥2 类、logistic 结局必须 0/1
```

**顺序本身就是设计**：先做便宜的静态检查，再做需要读数据的检查；有硬错误就不再报软提示，
避免一次给用户十几条噪音。

### 6.3 实现分工

| 文件 | 负责 | 特征 |
|---|---|---|
| `stats/methods.py` | 描述、缺失、正态/Levene、两组比较、ANOVA + 事后、卡方、相关、回归、logistic、趋势、聚合表 | 检验策略链的主战场（正态→Levene→失衡→最优/次优） |
| `stats/inference.py` | 单样本、随机区组、析因、重复测量、McNemar、样本量 | 设计类与教材第六至十章 |
| `stats/descriptive.py` | `classify_distribution`、完整描述、参考值范围 | 分布四态判定是单一入口 |
| `stats/survival.py` | KM / log-rank / Breslow / Cox / RMST | 教材 §14 + 外部标准（PH 检验、RMST） |
| `stats/impute.py` | MICE、简单插补、delta 扫描 | 数据产出型 |
| `stats/cleaning.py` | 去重/筛选/标准化/分箱/异常值/截尾 | 数据产出型（六工具） |
| `stats/significance.py` | SNK/Tukey/LSD/Schéffé/Dunnett/Dunn、p 调整、星号 | 只做分布与判定，不碰 DataFrame |
| `stats/plotting.py` | 12 类图 + 拼图 + 显著性比较线 + CJK 字体回退 | 失败不连带丢弃统计结果 |
| `stats/notes.py` | `METHOD_NOTES` 教材口径文案 | 宿主固定文案，不是模型生成 |

### 6.4 策略链：让用户看见「为什么」

以 `group_compare` 为例，`result["strategy"]` 至少包含：

```json
{"steps": ["Shapiro-Wilk 正态性检验：A 组 P=0.31、B 组 P=0.02 → 不满足正态",
           "非正态 → 选择 Mann-Whitney U（秩检验）"],
 "final_method": "mannwhitney",
 "alternative": "次优：t（当检验前提变化时使用）"}
```

它和执行结果一起进审阅卡（可展开）。这是「可解释」的落地方式：不是让模型解释，
而是执行期把决策点记下来。`method_note` 则回答「这个方法按哪本教材、哪一节、什么禁忌」。

### 6.5 数据产出型工具的三件套

`impute` 与六个清洗工具的约定完全一致：

1. 产物写 CSV：`imputed_step_{i}.csv` / `cleaned_step_{i}.csv`（`_artifact_dir` 由宿主注入，
   模型不可填写）；
2. 返回值里带 `_next_frame`（管道内部键），执行器消费后覆盖当前 `df`，供同链后续步骤使用；
3. service 在 `review_request` 之后读产物注册数据集，推 `dataset_added`——
   **只追加标签页，不切换 active**（切换会打断用户当前视图，且会导致「看到新表、分析旧表」）。

`sensitivity_only=true` 的方法（如 LOCF）不产出数据集：前向填充会系统性压缩方差，
只能进敏感性分析，不能当主分析结果。

### 6.6 图表

- `CHART_TYPES` 是枚举真相源；`none` 表示不出图；
- `render_chart` 按 `chart_type` 分支，`step.params` 提供布局/α 等；
- 组间比较图会调用 `_annotate_pairwise` 画比较线并标 `***/**/*/ns`（按校正后 p，最多 3 对）；
- CJK 字体检测失败时标题回退英文，避免「Glyph missing」与乱码；
- 渲染失败只写 `chart_error`，`StepResult.status` 仍为 success（前端显式提示「统计结果已生成但图表失败」）。

---

## 7. 前端：事件驱动的三栏工作台

### 7.1 组件树

```text
App.tsx（唯一状态所有者）
├── SessionTabs（会话标签 / 新建 / 删除 / 清理重复）
├── ChatPanel（会话流）
│   ├── PlanCard            方案卡（工作流图、步骤、依据、选项、估计目标）
│   │   └── PlanFlowView    流程图（节点依赖 + 参数展开 + Mermaid 文本）
│   ├── StepDeliveryCard    节点级交付（逐节点结果/错误 + 重跑 / AI 修正）
│   ├── TypeReviewCard      类型确认卡（讨论前置门控）
│   ├── AnalysisConfigCard  出图配置卡（图表/画板/α/校正）
│   ├── ReviewCard          审阅/交付卡（策略链、方法依据、解读）
│   ├── PlotSuggestCard     补图建议卡
│   ├── AnswerCard          答疑卡
│   └── ErrorCard / UploadZone / ThinkingCard
├── WorkspacePanel（工作区：画像 / 统计表 / 结果数据 / 执行产出，模块可折叠）
│   ├── ProfileTable（类型下拉 / AI 建议徽标 / 批量采纳）
│   ├── ResultTable（统计表 → CSV/XLSX/JSON）
│   └── ChartCard（图表 → PNG/JPG/PDF/TIF）
├── ChainBuilder（工具装配 Tab：推荐流程 / 能力目录表单 / 模板 / 方案导入）
└── CapabilityDrawer / UploadChoiceDialog / ErrorBoundary
```

### 7.2 五个状态维度

`App.tsx` 没有引入 Redux/Zustand，全部是 `Record<sessionId, …>` 的分桶状态：

| 维度 | 类型 | 为什么必须按会话分桶 |
|---|---|---|
| `messagesBySession` | `ChatMessage[]` | 切走再切回，聊天记录不能丢 |
| `phaseBySession` | `idle/thinking/chart_config/executing/interrupted/delivered` | 终结事件按 ownerSid 落地，不能被别的会话覆盖 |
| 交互卡 `chartConfig/typeReview/plotSuggest/columnSuggestions BySession` | 各卡片请求体 | 全局单份时切回后卡消失，而 phase 仍是 chart_config → 输入只读又无卡可确认，会话卡死 |
| `stepDeliveriesBySession` | `StepDelivery[]`（按 `index` 去重排序） | 节点级交付是「本轮执行」的中间态，新 `plan` 到达即清空；不能与别的会话混用 |
| `workspaces` | `WorkspaceTab[]`（含 `sessionId` 归属） | 平面数组会让右栏停在其他会话的表/图上（静默错看数据） |

`phase` 的语义：

| phase | 触发 | 界面 |
|---|---|---|
| `idle` | 初始 / plan / resumed(discussion) / error | 正常输入 |
| `thinking` | chat 发出、progress 非 executing | 思考气泡 + 中断按钮 |
| `chart_config` | `chart_config` 帧 | 出图配置卡，输入只读（避免被 SESSION_BUSY 拒绝后陷入死角） |
| `executing` | progress(stage=executing) / 确认执行 | 进度条 + 中断按钮 |
| `interrupted` | `interrupted` 帧 | 「继续」按钮 |
| `delivered` | `delivered` / `answer` | 输入框提示「针对结果提问」 |

### 7.3 事件 → 状态映射（`handleEvent`）

| 事件 | 前端动作 |
|---|---|
| `data_profile` | upsert 工作区；按 `active` 语义位决定是否改会话绑定 |
| `type_review` | 挂类型确认卡，phase → idle |
| `type_confirmed` | 撤卡、刷新画像、清空建议与加载态；按 `source`（type_review/ai/manual）生成可核对文案 |
| `column_type_suggestions` | 存建议列表 + 加载态复位，画像表显示徽标与理由 |
| `stream` | 累积到 `streamTextRef`，plan 到达时转成一条可折叠「思考过程」 |
| `plan` | 渲染方案卡（含 `flow`）；**清空上一轮节点交付**；清空过期 chart_config/plot_suggest；phase → idle |
| `chart_config` | 挂配置卡；phase → chart_config；清空 stream |
| `progress` | executing → 进度 + phase；其它 → thinking |
| `step_result` | 按 `index` upsert 节点交付；phase → executing（失败节点也更新，不中断） |
| `review_request` | 报告 upsert 到绑定工作区（无画像时建 `pending-{sid}` 占位）；push 审阅卡；phase → idle |
| `interpretation` | **补进最后一条审阅卡**（不新增消息） |
| `dataset_added` | 追加工作区标签，不切换 active；notice 区分插补/清洗 |
| `delivered` | 最后一条审阅卡标记 delivered；phase → delivered |
| `back_to_discussion` | phase → idle + notice |
| `answer` | 答疑卡；phase → delivered |
| `interrupted` | 停止进度、清空交互卡 |
| `resumed` | **按服务端 stage 校正 phase**（回放的历史 progress 不能把界面永久卡在「执行中」） |
| `chat_rejected` | notice 引导 + phase → idle |
| `error` | 错误卡 + 清空交互卡 + phase → idle |
| `*_user` | 回放用户动作气泡（review_user+revise →「修正意见：…」；retry_step_user →「重跑节点 N」；amend_step_user →「补充说明：…」） |

**一个容易忽略的细节**：`handleEvent` 里的 `isActive` 实时读 `activeChatIdRef.current`，
而不是闭包捕获的 `activeChatIdResolved`。事件到达瞬间用户可能已切走会话，闭包值过期会让
旧会话的帧写坏当前会话的显示状态（这是前端审计的实证修复项）。

### 7.4 连接生命周期

```text
切到会话
  ├─ 并行 1：GET /sessions/{sid}/workspace 拉快照 → 与本地按 dataset_id/report_id 幂等合并
  └─ 并行 2：connectSession
        onopen → 若 last_seq>0 或该会话是「后端恢复的」→ send {type:"resume", last_seq}
        onmessage → 记录 seq → handleEvent(sid, event)
        onclose(非手动)
           ├─ 4401/4403 → 停止重连、清 token、回登录卡
           └─ 其它 → 指数退避 1s→2s→…→10s 重连
```

**为什么快照与回放都要**：事件流会按阈值轮转，长会话的 `data_profile` 早已被裁掉；
只靠回放必然「左栏有、右栏空」。只靠快照又会丢聊天上下文（用户气泡不在快照里）。

### 7.5 上传与工作区绑定

三条入口（会话「+」/工作区「+」/全窗口拖拽）共用同一条管道：

```text
requestUpload(file)
  ├─ 当前会话未绑定数据 → handleUpload 直接上传（必要时新建会话）
  └─ 已绑定 → 挂起并弹 UploadChoiceDialog
        ├─ 加入当前工作区 → handleUpload(file, {sessionId})   # 后端新增标签
        ├─ 新建会话       → handleUpload(file, {forceNew:true})
        └─ 取消
```

多文件拖拽是**队列化**的：`pendingQueueRef` + Promise 让 `useFileDrop` 顺序等待。
单槽位会让后来的文件覆盖前一个而静默丢失。

**`active` 语义位**是这里最关键的一个约定：

- 只有「首次绑定」与「显式激活」才改会话绑定；
- 已绑定会话再上传只是新增标签（后端 `active_dataset_id` 不变）；
- 否则会出现「前端看到新表、后端分析旧表」的静默错分析。

切换标签必须走 `POST /sessions/{sid}/workspace/{dsid}/activate`（REST 而非 WS）：
跨会话切标签时 WS 正在重连，消息可能发不出去；REST 与连接状态解耦。

### 7.6 卡片族的交互细节

- **PlanCard**：顶部渲染 `PlanFlowView`（节点 = 工具、边 = 依赖，可展开参数/依据，附 Mermaid 文本）；
  显示估计目标五要素；缺失要素高亮提示；缺 `rationale` 显示「依据未提供（可让它补充说明）」；
  `confirm` 按钮提交中禁用；`custom/supplement` 展开输入框（补充要求后再发）。
- **TypeReviewCard**：讨论前的类型门控；逐列类型下拉 → 一条 `type_confirm` 提交全部列
  （宿主先整体校验再落库，避免半更新），确认后自动续跑挂起的 chat。
- **ProfileTable**：工作区里的画像表；「AI 确认类型」发 `suggest_column_types`，建议以
  「类型 + 置信度 + 理由」徽标展示，支持单列采纳与全部采纳——两者都走批量 PATCH
  （带 `source=ai`），由后端广播 `type_confirmed` 同步回会话区。
- **AnalysisConfigCard**：每步只列该工具支持的图（后端随 `chart_config.steps[].charts` 下发）；
  多图可选独立/同画板布局；α 与校正方式随计划下发；「使用默认」可跳过。
- **ReviewCard**：步骤状态点、图表直链、策略链折叠、方法依据折叠、解读内嵌、
  未核验数值角标、多重性提醒；未交付显示「确认交付 / 提出修正」，已交付显示「调整分析方案」。
- **PlotSuggestCard**：表格型步骤可补图（`plot_later`），补图后后端重发 `review_request{updated:true}`。
- **StepDeliveryCard**（047）：按节点列出「序号 / 状态 / 方法 / 是否已更新」；展开失败节点可见
  错误与 hint，并提供两条出口——「重跑该节点」（`retry_step`）与「补充说明让 AI 修正」
  （`amend_step`，输入框内容同时落一条用户气泡）。执行中按钮置灰（`busy`）。
- **ErrorCard**：把 `detail.issues` 渲染成结构化列表（步骤号 + 原因 + 修法），
  原始 JSON 退为二级折叠；`INVALID_PLAN` 不再只是「方案校验未通过」一行字。
- **AnswerCard**：答疑回答 + caveats + 未核验数值。

### 7.7 工作区与导出

- 标签按会话过滤；`activeWorkspace` 解析顺序：显式选择 → 会话绑定的数据集 → 第一个。
- 四个模块卡（数据画像 / 统计表交付 / 结果数据 / 执行产出）可独立折叠，默认展开——
  结果可见优先，折叠只是腾空间；折叠用 `aria-expanded` + 方向箭头。
- 统计表：CSV（UTF-8 BOM，Excel 直接打开）/ XLSX / JSON。
- 图表：PNG / JPG / PDF / TIF（后端按需重渲染，不缓存多格式）。
- 报告：风格（学术/轻量）× 格式（docx/pdf/md），带 `report_id` 可导出历史报告。
- 直链（图片/下载）不能带请求头，统一用 `withToken()` 追加 `?token=`。

### 7.8 工具装配（零模型的执行通道）

`run_chain` 是一条**完全绕过模型**的路径：

```text
ChainBuilder 拉取 /capabilities、/templates、/templates/builtin
  ├─ 推荐流程：选内置 recipe → POST /sessions/{sid}/chain/match（AI 优先，失败回退规则）
  │     → 占位槽位落到真实列，返回 steps + matched + warnings → 载入工作链（可继续手改）
  ├─ 手动装配：选工具（列类型与 accepts 不相交时置灰）→ 动态参数表单（列参数一律下拉）
  │     ├─ 目标列类型与 accepts 不符 → 实时提示 + 「一键设为分组列」（移出 target、填 group_param）
  │     └─ 编辑/排序工作链（可导入当前方案步骤、可存为模板、可导入导出 JSON）
  └─ onRun → WS run_chain
        → service：方法名宿主校验 → 构造 AnalysisPlan → validate_plan 硬校验
        → 直接执行（跳过 chart_config，图表已装配时选定）
```

这条通道的价值：统计师不需要「说服模型」就能精确控制每一步；也是回归测试
「执行层与模型解耦」的最好证据。推荐流程在此基础上再降一层门槛——**先给你一条符合
方法学规范的骨架，再由你在真实列上确认**，而不是从空白表单开始。

---

## 8. 契约速查

> 完整契约以 `spec/done/006-session-api.md` 与 `frontend/src/types.ts` 为准，此处只列形状。

### 8.1 WS 入站（前端 → 服务端）

| type | 关键字段 | 说明 |
|---|---|---|
| `chat` | `content` | 讨论 / 答疑 / 修正补充 |
| `confirm_plan` | — | 确认方案（有图步骤 → chart_config） |
| `chart_choice` | `choices[], layout, alpha, correction, use_default?` | 出图配置确认 |
| `review` | `decision: accept\|revise`, `content?` | 交付 / 修正 |
| `option` | `option_id`, `content?` | 方案卡选项 |
| `type_confirm` | `types: {列: 类型}` | 敲定列类型（确认后自动续跑挂起 chat） |
| `workspace` | `dataset_id` | 切换激活工作区（WS 版本，REST 亦可） |
| `plot_later` | `step_index`, `chart_type` | 表格步骤补图 |
| `run_chain` | `steps[]` | 手动装配链 |
| `retry_step` | `index`, `overrides?{params,target_columns,chart_type}` | 重跑该节点及下游（047，零模型） |
| `amend_step` | `index`, `note` | 模型只重写该节点后重跑（047） |
| `suggest_column_types` | — | 请求 AI 列类型建议 |
| `interrupt` | — | 中断当前任务 |
| `resume` | `last_seq?` | 重连补发 / 阶段回放 |

### 8.2 WS 出站（服务端 → 前端）

`data_profile`、`type_review`、`column_type_suggestions`、`type_confirmed`、`chat_rejected`、
`stream`、`progress`、`plan`、`chart_config`、**`step_result`**、`review_request`、`interpretation`、
`dataset_added`、`plot_suggest`、`answer`、`back_to_discussion`、`delivered`、
`interrupted`、`resumed`、`error`、`{type}_user`（仅回放；含 retry_step_user / amend_step_user）。

全部出站帧经 `EventLog` 注入单调 `seq`；错误帧固定形状
`{type:"error", code, message, hint, detail}`。`step_result` 帧带 `index/total`，
`step` 内再带一份 `index/total/updated`（重跑与拼图更新时 `updated=true`）。

### 8.3 核心数据形状

```ts
PlanStep { step_id?, title, method, target_columns[], chart_type, params, rationale?, depends_on? }
PlanFlow { nodes[{index,id,title,method,target_columns,params,chart_type,rationale,depends_on}],
           edges[{from,to}], order:number[], mermaid:string }
StepDelivery { index, total, updated?, title, method, status, result?, artifact?, table?, error? }
StepResult { title, method, status: "success"|"failed", result, artifact?, table?, error? }
ReportStep.table { columns: string[], rows: Record<string, unknown>[] }
```

`plan` 事件 = `{message, steps, flow?, options, estimand, sap_status}`；`flow` 缺省时
前端只渲染步骤列表（旧后端兼容）。`step_result` 与最终 `ExecutionReport.steps[]` 同形，
差别是多了 `index/total/updated`——这样「中间交付」与「最终报告」用同一套渲染逻辑。

`result` 里与前端/解释相关的约定键：

| 键 | 含义 |
|---|---|
| `strategy {steps[], final_method, alternative}` | 检验策略链 |
| `method_note` | 教材口径说明（宿主文案） |
| `multiplicity_warning` | 多重性提醒（多组两两比较） |
| `chart_error` | 图表渲染失败原因（统计结果仍有效） |
| `imputed_dataset` / `cleaned_dataset` | 数据产出型工具的产物元信息 |
| `table` | 可导出表格（列 + 行） |

### 8.4 错误码（16）

`MODEL_UNAVAILABLE`、`MODEL_REQUEST_FAILED`、`DATA_REQUIRED`、`INVALID_PLAN`、
`MISSING_PARAM`、`INVALID_PARAM`、`COLUMN_NOT_FOUND`、`COLUMN_TYPE_MISMATCH`、
`ORDINAL_HINT`、`TOOL_NOT_FOUND`、`INSUFFICIENT_DATA`、`EXECUTION_FAILED`、
`INTERRUPTED`、`NO_ACTIVE_RUN`、`SESSION_BUSY`、`PROTOCOL_UNSUPPORTED`。

与注册表 `HARD_ISSUE_CODES` 对应的 6 个码（`TOOL_NOT_FOUND` / `COLUMN_NOT_FOUND` /
`MISSING_PARAM` / `INVALID_PARAM` / `INSUFFICIENT_DATA` / `COLUMN_TYPE_MISMATCH`）会阻断执行；
`ORDINAL_HINT` 是软提示；`PROTOCOL_UNSUPPORTED` 专指协议顺序/未知消息，不要与
`INVALID_PLAN`（方案要改）混用。

### 8.5 REST 路由

| 方法与路径 | 用途 |
|---|---|
| `POST /sessions` / `GET /sessions` / `DELETE /sessions/{sid}` | 创建 / 列表（按 owner）/ 删除（含磁盘痕迹） |
| `POST /sessions/cleanup_duplicates` | 按绑定文件名分组保留最新 |
| `POST /sessions/{sid}/data` | 上传（≤50MB，行数 ≤ `MEDSTA_MAX_ROWS`） |
| `PATCH /sessions/{sid}/workspace/{dsid}/columns` | 单列或批量改类型（整体校验） |
| `GET /sessions/{sid}/workspace` | 工作区快照（刷新后右栏真相源） |
| `POST /sessions/{sid}/workspace/{dsid}/activate` | 激活工作区（落快照） |
| `GET /capabilities` | 工具目录 + 图表 + planned 缺口 |
| `GET /export/{sid}/{step_index}` | 表格 CSV/XLSX/JSON；图表 PNG/JPG/PDF/TIF |
| `GET /report/{sid}?style=&format=&report_id=` | docx/pdf/md |
| `GET/PUT/DELETE /templates[/{name}]`、`GET .../export`、`POST /templates/import` | 工作链模板 |
| `GET /templates/builtin` | 内置推荐流程（recipe 目录，只读） |
| `POST /sessions/{sid}/chain/match` | 推荐流程占位槽位 → 真实列（AI 优先，规则兜底） |
| `POST /auth/login` | 多用户登录换令牌 |
| `WS /ws/{sid}` | 会话双向通道 |

---

## 9. 开发流程与质量门

### 9.1 spec 驱动（目录即状态）

```text
spec/draft → designing → implementing → done        放弃 → archived
```

进入 `implementing` 的门槛（缺一不可）：

1. 行为列表完整且可测（每条是可观察的外部行为）；
2. 验收标准明确（硬门=确定性测试 / 软标=语义质量）；
3. 测试映射完成（每条行为 → 哪个公共接口测试）；
4. 涉模型输出时，结构化契约已声明（字段/类型/语义/可空性/约束）。

### 9.2 TDD 垂直切片

一条行为 → 一个测试（先确认 RED，且失败原因正确）→ 最小实现（GREEN）→ 下一条。
禁止「先写全部测试再写全部实现」。测试走公共接口，只在模型调用与文件系统边界 mock。

### 9.3 四层测试金字塔

| 层 | 入口 | 隔离手段 | 关注点 |
|---|---|---|---|
| 方法层 | `execute_step`、`profile_dataframe`、`render_chart` | `tmp_path` 作为产物目录 | 数值口径、策略链、PNG 契约 |
| 编排层 | `SessionService.handle`、`AnalysisWorkflow` | 注入假 gateway / request_factory | 状态机、事件序列、记录分桶 |
| 契约层 | `TestClient` + `websocket_connect` | `app.state.data_root` 指向 tmp；`manager.clear()` | 请求/响应/事件形状、错误码、归属 |
| 前端层 | Vitest + RTL / Playwright | 只 mock `fetch`/`WebSocket`；E2E 用桩模型后端 | 布局、交互、前后端契约 |

三条测试纪律：

- 测试不写真实 `backend/data`、不依赖 `.env`（机制：conftest 重定向数据根 + 强制 `build_gateway` 抛错）；
- 真实模型用例只在 `tests/test_real_llm_smoke.py`，`MEDSTA_REAL_LLM=1` 才跑；
- 疑似卡死用 `pytest -o faulthandler_timeout=60` 转储线程栈。

047/048 的增量都有独立守护：`test_flow_graph`（图/依赖/降级）、`test_step_delivery`（节点交付/
失败隔离/重试）、`test_session_context`（分层与 snapshot 预算）、`test_stats_skills`（挑选与裁剪）、
`test_rationale_repair`（补全成功/失败/不额外调用）、`test_chain_recipes`（候选/复核/回退）。
前端对应 `PlanFlow.test.tsx`、`App.stepDelivery.test.tsx`、`ChainBuilder.recipes.test.tsx`。

### 9.4 文档守护（一致性可执行）

`backend/tests/test_docs_consistency.py` 把「文档必须与代码同源」变成断言：

- 附录 A 工具清单 == 注册表；
- `docs/tools.md` ⊇ 注册表且无已注销工具、覆盖全部图表类型与中文名；
- 附录 B 状态表 == `SessionStatus`；事件表 ⊇ 实际下发事件；
- README 不写易过期计数；
- README/架构/产品/统计四份文档的相对链接必须可达；
- 产品说明的能力矩阵必须覆盖全部工具。

**这意味着：加一个方法/事件/状态，不改文档就跑不过测试。**

### 9.5 变更三件套（强制）

每次变更必须同时：

1. `docs/timeline.md` **顶部**追加一行（日期 ｜ 类型 ｜ 内容 ｜ 原因/依据，严格倒序）；
2. 更新 `TO_DO.md` 的进行中 / 已完成清单；
3. 跨模块架构决策的完整推理写进 `docs/design-notes.md`。

三者缺一，视为变更未完成。

### 9.6 CI

三个作业：backend（ruff + mypy + pytest + 覆盖率门槛）、frontend（lint + build + vitest）、
e2e（Playwright + 桩后端）。`scripts/ci.sh` 是本地等价镜像（`CI_SKIP_E2E=1` / `CI_SKIP_COVERAGE=1`
可跳）。覆盖率门槛与实测基线见 [评估基线](./evaluation-report.md)。

---

## 10. 动手实验

每个实验都给出「改哪里 → 怎么验证 → 会触发哪些守护」。

### L1（读）追一个数字的来路

1. 上传一张两列表，`chat`「比较两组疗效」；
2. 在 `plan` 里找到 `method` 与 `target_columns`；
3. 打开 `stats/methods.py::group_compare`，对照 `strategy.steps` 找到每一个分支；
4. 在 `review_request.steps[0].result` 里核对 `statistic/p_value/ci95` 与代码输出键一致。

**验收**：你能说清「为什么这次走了 Welch 而不是 t」以及这个判断写在哪一行。

### L2（写）新增一个统计工具

1. 复制 `spec/templates/spec-template.md` 建 spec；
2. `stats/` 里实现 handler（纯函数，返回 dict，含 `strategy` 与 `table`）；
3. `registry.py` 登记 `ToolSpec`（params/charts/task/applicability/accepts）；
4. `agents/discussion.py::MethodType` 加名字；`stats/notes.py` 加口径；`CHART_TYPES` 若需新图再改；
5. 同步 `docs/architecture.md` 附录 A、`docs/tools.md`、`docs/product-guide.md`；
6. 运行 `cd backend && pytest tests/test_method_contract.py tests/test_docs_consistency.py tests/test_json_contract.py`。

**验收**：三处守护全绿；`/capabilities` 能看到新工具；装配器能选到它并跑通。

### L3（写）新增一个前端交互事件

1. 后端：`service.handle` 的 handler 表加分支 → 至少一处 `send({"type": ...})`；
   若是用户动作，还要加进 `USER_ACTION_EVENTS`（回放帧 `<type>_user`）；
2. 前端：`types.ts` 的 `WsEvent` 加联合类型；`App.handleEvent` 加 case；
   若是「执行中间态」，参照 `step_result` 用 `Record<sessionId, …>` 分桶并在终结事件里清理；
3. 契约测试：`tests/test_ws_contract.py` 增断言；`tests/test_docs_consistency.py::test_appendix_b_covers_emitted_ws_events` 要求附录 B 登记；
4. 文档：`docs/architecture.md` 附录 B + `frontend/src/types.ts` 同步。

**验收**：守护测试全绿（漏登记附录 B 会直接失败）。

### L4（写）让一个状态转移非法

1. 在 `_ALLOWED_TRANSITIONS` 里删掉一条边；
2. 写一个测试：构造该源状态 → 调 `manager.transition` 到目标状态 → 断言 `InvalidStateTransition`；
3. 走 WS 路径再测一次：应收到 `PROTOCOL_UNSUPPORTED` 而非断连。

**验收**：`handle` 的错误转换路径被覆盖；真实前端不会白屏。

### L5（写）给解读加一条硬门

1. 在 `agents/interpretation.py` 加一个模式（例如禁止「治愈/根治」类断言）；
2. 在 `_sanitize` 的硬门列表里使用它；
3. 写测试：注入假 gateway 返回命中文本 → 断言 `interpret` 返回 None（重试后仍命中）或文本被拒。

**验收**：只影响生成侧，不影响统计结果与审阅卡结构。

### L6（写）加一张前端卡片

1. `types.ts` 加消息类型或事件类型；
2. `chat/` 新建组件（纯展示，回调上报）；
3. `ChatPanel` 挂载；`App` 里按 sessionId 分桶存请求体，terminate 事件里清空；
4. 写 RTL 测试：渲染 → 点击 → 断言回调参数。

**验收**：切走会话再切回，卡片仍在（分桶生效）。

### L7（写）一条失败路径测试

选一个最容易静默失败的点：`numpy.bool_` 进表格。

1. 构造一个返回 `np.bool_` 的假工具结果；
2. 断言 `PipelineExecutor.execute` 的 `report.steps[0].table` 是 Python `bool`；
3. 断言 `json.dumps(..., allow_nan=False)` 不抛异常。

**验收**：`test_json_contract` / `test_execution_report` 同类断言通过。

### L8（用）零模型复现一次分析

1. 打开「工具装配」Tab；
2. 选 `describe` → 目标列全选 → 存为模板；
3. 再加 `group_compare`（分组列 + 数值列）→ 运行；
4. 观察：不经过任何模型调用，直接收到 `review_request`。

**验收**：`MedSta` 的「可复现」承诺在你自己手上被验证一次。

### L9（写）节点失败与两条恢复路径（047）

1. 打开 `backend/tests/test_step_delivery.py`，找到「失败节点不阻断后续」的构造；
2. 用假工具让第 2 个节点抛错，断言 `report.steps[1].status == "failed"`、
   `report.steps[2].status == "success"`；
3. 调 `service.handle(session_id, {"type":"retry_step","index":1,"overrides":{"params":{...}}}, send)`，
   断言只从 index 1 起重跑（index 0 的 `step_result` 不再出现），最终 `review_request.updated == true`；
4. 用注入替身的讨论智能体调 `amend_step`，断言替换后的节点保留原 `depends_on` / `step_id`，
   且发送了一条新的 `plan`（含 `flow`）。

**验收**：你能说清「为什么重跑不会重新走 `EXECUTING → DELIVERED`」以及忙锁挡在哪。

### L10（写）加一条统计 skill 与一条推荐流程（048）

1. `agents/stats_skills.py::SKILLS` 加一条 `StatsSkill`（`keywords/when/rules/pitfalls/reporting`）；
2. `agents/chain_recipes.py::RECIPES` 加一条 `Recipe`（`targets` 与 `params` 用占位槽位）；
3. 写测试：`select_skills("…")` 能命中新条目；`match_recipe` 在缺列时给 warning 而不是产错链；
   模型返回候选外的列时被忽略并回退规则候选（`candidates_for` 边界）；
4. `GET /templates/builtin` 自动出现新流程（前端不需要改代码）。

**验收**：装配区能看到新推荐流程；「AI 匹配」失败时仍能按规则载入。

---

## 11. 排错手册

| 现象 | 根因 | 去看 |
|---|---|---|
| 刷新后左栏有、右栏空 | 只靠事件流重建，`data_profile` 已被轮转裁掉 | `hydrateWorkspace`；`GET /sessions/{sid}/workspace` |
| 右栏堆出重复统计表/图 | 回放重放历史 `review_request`，未按 `report_id` 去重 | `upsertReport` |
| 切会话后右栏还是别的会话的表 | `WorkspaceTab` 缺 `sessionId` 归属 | `sessionWorkspaces` 过滤 |
| 界面永久停在「执行中」 | 回放的历史 `progress` 覆盖了真实 phase | `resumed` 帧的 `stage` 校正 |
| 看到新表、分析旧表 | 标签切换只改本地，没同步后端 `active_dataset_id` | `handleActivateWorkspace` + REST activate |
| 出图配置卡消失且输入被拒 | error 帧清卡后 phase 仍是 `chart_config` | `ChatPanel` 的 `awaitingChartConfig` |
| 方案卡没有工作流图 | `plan.flow` 缺省（旧后端 / 服务未重启） | 重启 dev 栈；`PlanFlowView` 仅在 `flow` 存在时渲染 |
| 节点失败后整条链作废 | 前端未接 `step_result`，或后端未发节点交付 | `_step_result_sender` + `App` 的 `step_result` 分支 |
| 重跑提示「没有可重试的执行」 | 进程重启后 `_reports`/`_plans` 为空（只在内存） | 重新确认方案执行；这是有意的内存边界 |
| 节点修正后图结构乱了 | amend 未保留 `depends_on`/`step_id` | `_on_amend_step` 的 `model_copy(update=...)` |
| 类别列误用提示仍只说「可用 chi_square」 | 旧版 hint / 未重启 | `validate_step` 的 `spec.group_param` 分支 |
| 推荐流程载入少了几步 | 组合后 `validate_step` 硬错误 → 主动移除并给 warning | 看返回的 `warnings`，不是静默丢失 |
| 推荐流程缺列但仍有步骤 | AI 失败已回退规则匹配，或候选为空 | 返回的 `matched[].by`；`candidates_for` |
| 重跑下游后结果与首次不一致 | 后端仍是 2026-11-21 之前的进程（未重放上游 `_next_frame`） | 重启 dev 栈；现行逻辑在 `_input_frame` |
| AI 修正仍提示「该节点之前失败」 | 后端仍是旧进程（重跑未回写上下文） | 重启 dev 栈；现行逻辑在 `_rerun_from` 的 `_mark_node` |
| 工作区快照 404（前端顶部横幅） | 后端进程是旧代码（无 `/workspace` 路由） | 重启 dev 栈；日志见 `logs/dev.log`（`--log-file`） |
| 工作台改了类型、会话区没记录 | REST 未走 `service.broadcast`（旧代码） | `routes_data.patch_columns` 的 `broadcast` |
| 讨论偶发 `EXECUTION_FAILED`（SQLite 锁） | `_record` 写入失败被当作主流程失败 | `_record` 已旁路化：只记 warning |
| 中断按钮点了没反应 | 执行在 handler 里同步阻塞 | `workflow.create/start` 拆分 + `_execution_task` |
| 同会话双跑 / 中断失效 | 旧任务无条件清掉新任务槽位与忙锁 | `_release_task_slot` 的 `current_task()` 判定 |
| 交付后提问仍出新方案 | 交付态未走答疑（`_interpret_agent` 为空） | `_on_chat` 的 DELIVERED 分支 |
| 答疑一次失败后永久 SESSION_BUSY | `_answer_task` 缺 `finally` 释放 | `_answer_task` |
| 图表不显示但统计结果正常 | 渲染失败只写 `chart_error` | `ReviewCard` 的 chart_error 提示 |
| 前端整帧收不到、卡在执行中 | `result` 含 NaN/numpy 标量导致 `send_json` 抛错 | `_jsonify`（含 `table`） |
| `.xls` 上传 400 | 缺 `xlrd`（pandas 的 .xls 引擎） | `pyproject.toml` + `load_table` 提示 |
| prod + 鉴权整页 401 | 静态外壳未放行 | `_is_public_shell` |
| 后端重启后前端一直 401 | 令牌在内存表，重启即失效 | WS `4401/4403` → 回登录卡 |
| 测试挂死且无输出 | 真实 `.env` 被应用 / 后台任务未收尾 | `_no_real_gateway`；`wait_idle`；`faulthandler_timeout` |

---

## 12. 代码地图

| 文件 | 一句话职责 | 先看哪个符号 |
|---|---|---|
| `main.py` / `medsta/launcher.py` | 一键启动（dev 双进程 / prod 单端口；`--log-file` 落盘） | `run_dev`、`build_prod_commands` |
| `medsta/app.py` | 应用工厂、鉴权中间件、路由挂载、SPA 托管 | `create_app`、`auth_guard`、`_build_service` |
| `medsta/config.py` | provider 配置、ModelGateway、流式与增量解析 | `build_settings`、`request_structured_stream` |
| `medsta/errors.py` | 16 个错误码与统一事件形状 | `AppError.to_event` |
| `api/routes_session.py` | 会话创建/列表/删除/登录/批量清理 | `login`、`list_sessions` |
| `api/routes_data.py` | 上传、列类型、工作区快照/激活 | `upload_data`、`patch_columns` |
| `api/routes_capabilities.py` | 工具目录 + planned 缺口 | `_PLANNED` |
| `api/routes_export.py` | 表格与图片导出（公式注入防护） | `_sanitize_frame`、`export_step` |
| `api/routes_report.py` | 报告 docx/pdf/md | `export_report` |
| `api/routes_templates.py` | 模板 CRUD + 导入导出 + 内置推荐流程 + chain/match | `save_template`、`list_builtin_recipes`、`match_chain_recipe` |
| `api/ws.py` | WS 薄封装（鉴权/锁/seq/补发） | `session_ws`、`send` |
| `session/manager.py` | 会话对象与状态机 | `_ALLOWED_TRANSITIONS`、`attach_data` |
| `session/service.py` | 全部消息编排、节点交付、重试/修正、后台任务 | `handle`、`_on_chat`、`_execution_task`、`_on_retry_step`、`_on_amend_step` |
| `session/context.py` | 会话上下文（owner→session 分层、节点状态、snapshot） | `SessionContextStore`、`SessionContext.snapshot` |
| `session/persistence.py` | 会话快照（原子写/恢复/删除） | `save`、`load_all`、`delete` |
| `session/events.py` | 事件流（seq/追加/轮转/补发） | `commit`、`read_after`、`_rotate` |
| `session/templates.py` | 工作链模板存取 | `is_safe_name`、`save` |
| `agents/discussion.py` | 方案契约与讨论提示（rationale 补全 / depends_on / 定点修正） | `AnalysisPlan`、`_ensure_rationales`、`amend_step` |
| `agents/flow.py` | `steps[].depends_on` → 节点/边/拓扑序/mermaid | `plan_flow`、`_coerce_deps` |
| `agents/stats_skills.py` | 内置方法学 skills（挑选 + 长度裁剪） | `SKILLS`、`skills_for_request` |
| `agents/chain_recipes.py` | 内置推荐流程（占位槽位 + 候选筛 + 规则匹配） | `RECIPES`、`candidates_for`、`match_recipe` |
| `agents/chain_match.py` | 模型在宿主候选内挑列（一次请求） | `ChainMatchAgent.match` |
| `agents/interpretation.py` | 证据白名单、硬门、截断、答疑 | `build_evidence`、`_sanitize`、`interpret` |
| `agents/type_advisor.py` | 列类型建议 | `ColumnTypeAdvisor.advise` |
| `pipeline/executor.py` | 计划派发、节点交付、单步隔离、JSON 归一、拼图 | `PipelineExecutor.execute`、`execute_node`、`_jsonify` |
| `pipeline/workflow.py` | TriggerFlow 编排与句柄 API | `_build_flow`、`create/start/wait_for_review/review/cancel` |
| `stats/registry.py` | 工具单一真相源 + 校验 + 派发 | `ToolSpec`、`validate_step`、`execute_step_with_frame` |
| `stats/methods.py` | 检验策略链主实现 | `group_compare`、`anova`、`chi_square` |
| `stats/inference.py` | 设计类方法与样本量 | `one_sample_test`、`factorial_anova`、`sample_size` |
| `stats/descriptive.py` | 分布判定、完整描述、参考值范围 | `classify_distribution` |
| `stats/survival.py` | KM/log-rank/Cox/RMST | `km_estimate`、`cox_fit` |
| `stats/impute.py` / `stats/cleaning.py` | 数据产出型工具 | `impute`、`_next_frame` 约定 |
| `stats/significance.py` | 事后比较分布与 p 调整 | `snk_step_down`、`p_adjust` |
| `stats/plotting.py` | 12 类图 + 拼图 + 显著性标注 | `render_chart`、`render_combined` |
| `stats/notes.py` | 教材口径文案 | `METHOD_NOTES` |
| `data/parser.py` / `data/profiler.py` | 解析与画像（四槽位） | `load_table`、`profile_dataframe`、`apply_column_type` |
| `reporting.py` | 报告中间表示 × 三种渲染 | `build_report_document`、`render_docx` |
| `frontend/src/types.ts` | 前后端契约镜像 | `WsEvent`、`PlanEvent`、`PlanFlow`、`StepDelivery` |
| `frontend/src/App.tsx` | 状态所有者与事件路由（五类分桶状态） | `handleEvent`、`hydrateWorkspace`、`handleUpload` |
| `frontend/src/api/client.ts` | REST + WS 封装 | `connectSession`、`withToken`、`matchChainRecipe` |
| `frontend/src/chat/ChatPanel.tsx` | 会话流与输入门控 | `inputDisabled`、卡片挂载 |
| `frontend/src/chat/PlanFlowView.tsx` | 工作流图（节点/依赖/参数/Mermaid） | `PlanFlowView` |
| `frontend/src/chat/StepDeliveryCard.tsx` | 节点级交付与重跑/定点修正入口 | `StepDeliveryCard` |
| `frontend/src/chat/ErrorCard.tsx` | 结构化 issues（步骤 + 原因 + 修法） | `planIssues` |
| `frontend/src/workspace/WorkspacePanel.tsx` | 画像/表格/图表/导出（模块可折叠） | 报告聚合与导出链接 |
| `frontend/src/builder/ChainBuilder.tsx` | 装配器（推荐流程 / 参数表单 / 模板） | `loadRecipe`、`run_chain` 提交 |

---

## 13. 术语与延伸阅读

**继续读什么**

| 想知道 | 去哪 |
|---|---|
| 三张分层/策略/时序图 | [architecture.md](./architecture.md) |
| 每个方法的公式、适用条件、教材章节 | [statistics-methods.md](./statistics-methods.md) |
| 产品边界、能力矩阵、交互旅程 | [product-guide.md](./product-guide.md) |
| 每个决策的推理与被推翻的方案 | [design-notes.md](./design-notes.md) |
| 什么时候改了什么 | [timeline.md](./timeline.md) |
| 某个功能的完整行为列表 | `spec/done/NNN-*.md` |
| 开发流程与 TDD 规则 | [spec/README.md](../spec/README.md) |
| 当前还剩哪些缺口 | [evaluation-report.md](./evaluation-report.md)、[TO_DO.md](../TO_DO.md) |

**最后一条教学建议**

读这个项目时，不要从「文件」入手，从「一次请求」入手：
在 `SessionService.handle` 打一个日志，发一条 `chat`，然后跟着日志走完整条链
（预筛 → 门控 → 模型 → 校验 → plan → confirm → chart_config → 执行 → review → interpret → deliver）。
走完一遍，你会比读十遍目录更理解它。

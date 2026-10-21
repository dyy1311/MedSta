# MedSta 设计思路与关键决策记录

> 记录跨模块的架构决策与理由。单功能的设计细节写在对应 spec 内；本文只放"需要读多个文件才能理解"的决策。

## 1. Agently Owner 划分（依据 agently skill 的所有权规则）

原则：**模型只拥有语义决策；schema 校验、枚举约束、算术与副作用全部归宿主代码。**

| 职责 | Owner | 说明 |
|---|---|---|
| 一次模型交互与输出契约 | `ModelRequest` | 方案生成 / 结果解释 / ReAct 推理，用 `.input/.info/.instruct/.output` 四段式声明结构化输出；每个消费字段的类型、语义、可空性、取值范围显式声明 |
| 一次 ReAct 讨论回合 | `AgentExecution` | 讨论态智能体运行，选择 producer、controls 与流 |
| Pipeline 应用层编排 | `TriggerFlow` | "确认→执行→交付→修正回讨论"是开发者拥有的编排：分支（修正分支）、顺序步骤、运行状态与恢复 |
| 会话/任务信息 | `TaskContext` | 消费者绑定的信息读取，不手工拼接全局上下文 |
| 数据文件与 artifact | `TaskWorkspace` | 上传数据集、生成的图表文件统一归 workspace |
| 会话与执行记录 | `RecordStore` | 可恢复的持久记录，支撑回溯与再对齐 |

反模式禁止：自定义状态存储、重试管理器、关键词/正则做语义判断、未经消费的输出字段、把原始数据全量塞进 prompt。

## 2. 模型输出契约：AnalysisPlan

讨论态最终产出结构化 `AnalysisPlan`（步骤数组：步骤名、统计方法、目标列、图表类型、参数），由宿主代码做 schema 校验后进入执行态。模型不产出可执行代码——pipeline 步骤是宿主实现的确定性操作（统计/预测/绘图），模型只决定"用哪一步、什么参数"。这保证执行可测试、可复现、可解释。

## 3. TDD 约定（依据 tdd skill）

- 垂直切片：一个行为 → 一个测试（RED）→ 最小实现（GREEN）→ 下一行为。禁止先写全部测试再写全部实现。
- 测试走公共接口（API/服务层函数），不测私有方法；仅在模型调用与文件系统边界使用模拟/临时目录。
- 模型相关测试：默认模拟模型验证结构化契约与确定性分支；真实模型调用仅做最小的、显式标记的验证（可跳过）。
- spec 的行为列表即测试循环队列，spec 敲定（进入 implementing）才开始写测试。

## 4. 会话状态机

会话状态：`discussing（讨论态）→ plan_confirmed（方案确认）→ executing（执行中）→ delivered（已交付）→（修正意见）→ discussing`。
状态由宿主 `SessionManager` 管理（确定性状态机，非模型决策）；模型只参与 discussing 态的内容生成。

## 5. 流式与持久化策略

- WebSocket 推送讨论消息、pipeline 步骤进度、artifact 就绪事件。
- 数据解析在任务内一次性完成并缓存画像，后续讨论只携带画像摘要而非全量数据（避免上下文膨胀）。
- 绘图后台生成文件，就绪后推送事件引用 artifact 路径，不在消息体里内联大图。

## 6. 生命周期与时间线

- spec 生命周期：`draft → designing → implementing → done`，放弃则 `archived`；规则见 `spec/README.md`。
- 每次流转在 `docs/timeline.md` 追加一行（日期、spec、动作、说明），保证治理可审计。

## 7. 测试架构（spec 019）

四层金字塔，越往下越依赖真实实现，仅在系统边界（模型网络调用、文件系统）注入假实现：

| 层 | 入口 | 隔离手段 | 关注点 |
|---|---|---|---|
| 方法层 | `stats.registry.execute_step`、`data.profiler`、`plotting.render_chart` | `tmp_path` 作为 artifact 目录 | 数值口径、策略链、PNG 产物契约 |
| 编排层 | `SessionService.handle`、`AnalysisWorkflow` | 注入 `RecordingFakeRequest` / 假 gateway | 状态机、事件序列、记录分桶 |
| 契约层 | `TestClient` REST + `websocket_connect` | `app.state.data_root` 指向 `tmp_path`，`SessionManager.clear()` 清场 | 请求/响应/事件契约、错误码 |
| 前端层 | Vitest + Testing Library / Playwright | 只 mock `fetch` 与 `WebSocket`；浏览器层用桩模型后端 | 布局、交互、前后端契约 |

关键决策：

- **数据根请求期解析**：`routes_data.DATA_ROOT` 原本是导入期常量，测试会污染真实 `backend/data/sessions`。
  改为请求期读取 `request.app.state.data_root`（回退环境变量），`create_app()` 注入同一路径；
  生产行为零变更，测试只需覆盖 app state。
- **全局单例清场**：`SessionManager` 是模块级单例，`clear()` 是显式测试接缝，避免测试间串味；
  不为测试引入依赖注入框架。
- **桩模型后端**：`backend/tests/e2e_app.py` 以 `create_app()` 为基础替换 `app.state.service` 的 agent，
  供 Playwright `webServer` 启动；不触碰生产装配路径。
- **真模型隔离**：`tests/test_real_llm_smoke.py` 用 `MEDSTA_REAL_LLM=1` 且存在 `LLM_API_KEY` 才运行，
  并在 `pyproject.toml` 注册 `real_llm` marker，默认 CI 不消耗额度。
- **前端代理可参数化**：`vite.config.ts` 的 proxy target 读 `MEDSTA_API`，E2E 用 5174→8021，
  与本地 dev（5173→8000）互不干扰。

## 8. 正确性护栏（spec 020）

- **列名词元匹配而非子串**：`age` 是 `stage`/`percentage` 的子串，英文列名按 `[^a-z0-9]+` 切词后与白名单求交集；
  中文（年龄/血压…）无词边界，使用子串匹配。列名只作为辅助信号，用户仍可在类型确认卡修正。
- **整数测量变量判连续**：列名命中白名单优先；否则非负且 `max-min ≤ 10` 判 `ordinal`（Likert/评分/分级），
  宽范围整数计数判 `continuous`；0/1 保持 `ordinal` 以免波及类型映射契约。
- **Logistic 分离三重检测**：未收敛、`max|β| ≥ 15`（OR≈3.3e6）、OR/CI 非有限，任一命中即拒绝并给出可操作建议。
  阈值取安全方向：宁可拒绝输出，也不下发不可估计的 OR；Firth 惩罚留作后续能力。
- **协议错误码独立**：未知 WS 消息用 `PROTOCOL_UNSUPPORTED`，`INVALID_PLAN` 只表示方案校验失败，
  避免前端把「版本不匹配」误读为「方案要改」。

## 9. CI 流水线（spec 021）

- **三作业并行**：backend（pytest + 覆盖率门槛）、frontend（lint/build/vitest）、e2e（Playwright）。
  拆分依据是失败定位与运行环境：E2E 需要 Python + Node 双环境，独立成 job 不污染前后端。
- **覆盖率门槛按实测定**：2026-10-21 语句覆盖率 88.19%，门槛取 83%（向下取整再 −5pt），
  目的是防大幅倒退而非追求数字；前端沿用 v8 报告，暂不设硬阈值。
- **E2E 安装 CJK 字体**：Ubuntu runner 默认无中文字体，安装 `fonts-noto-cjk` 以覆盖真实中文图表路径；
  不安装时英文回退也能通过，但会失去该路径验证。
- **本地镜像脚本**：`scripts/ci.sh` 复用同一组命令，解决「没有远端就无法验证流水线」的问题；
  通过 `COVERAGE_MIN=99` 实测过失败会立即中断并透传非零退出码。
- **推送与保护分离**：代码推送到 `main` 后 Actions 自动运行；分支保护（CI 必过）属于仓库设置，
  脚本无法代劳，需在 GitHub 后台手动开启。

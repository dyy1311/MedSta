# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

MedSta：面向数据研究者的轻量级 AI 数据统计分析/预测/绘图及解释智能体（Web 端）。上传数据 → 解析画像 → ReAct 讨论生成结构化分析方案 → 确认后 Pipeline 执行 → 交付图表与解释建议 → 可修正再执行。

## 常用命令

```bash
# 环境（用户使用 mamba，环境名 Sta；shell 未初始化时先 eval "$(mamba shell hook --shell bash)"）
mamba activate Sta

# 后端依赖安装（pip 直连困难时加 -i https://pypi.tuna.tsinghua.edu.cn/simple）
cd backend && pip install -e ".[dev]"

# 运行全部后端测试（当前 365 collected：364 passed + 1 项真模型跳过）
cd backend && pytest

# 运行单个测试
cd backend && pytest tests/test_pipeline.py -k "test_forecast_step"

# 真实模型冒烟（显式开启，消耗额度；默认 skip）
cd backend && MEDSTA_REAL_LLM=1 pytest tests/test_real_llm_smoke.py -q

# 一键启动（项目根，dev 模式：后端 8000 + 前端 5173，Ctrl+C 整组退出）
cd /home/xdy/MedSta && python main.py
# 注意：dev 的 uvicorn 无 --reload（reload 会让每次改动都触发启动期全量快照恢复）——
# 代码更新后必须重启 dev 栈才生效；就绪判据 = curl http://localhost:8000/health

# prod 模式（构建前端后由 8000 单端口托管 SPA+API；app.py 按 frontend/dist 存在性自动启用托管）
cd /home/xdy/MedSta && python main.py --prod

# 启动后端（http://localhost:8000，/health 健康检查）
cd backend && uvicorn medsta.app:app --reload --port 8000

# 前端（Vite 5 + React 18 + TS + Tailwind 3，dev 端口 5173，已代理 /sessions /auth /report /templates /capabilities /export /data /ws 到 8000）
cd frontend && npm install
cd frontend && npm run dev      # 开发
cd frontend && npm run build    # 构建（tsc -b && vite build）
cd frontend && npm run lint     # ESLint
cd frontend && npm test         # Vitest + Testing Library（jsdom，仅 mock fetch/WebSocket）
cd frontend && npm run test:coverage
cd frontend && npm run test:e2e # Playwright（自动起 8021 桩后端 + 5174 Vite）

# 本地 CI 镜像（等价 .github/workflows/ci.yml：后端 ruff + mypy + pytest+覆盖率门槛、前端 lint/build/vitest 覆盖率、E2E）
bash scripts/ci.sh
CI_SKIP_E2E=1 bash scripts/ci.sh   # 跳过浏览器端
CI_SKIP_COVERAGE=1 bash scripts/ci.sh  # 跳过后端覆盖率门槛
```

模型配置：复制 `.env.example` 为项目根 `.env`，填 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（OpenAI 兼容接口）。`ProviderConfig.from_env()` 会自动加载项目根 `.env`（不覆盖已显式 export 的变量）。未配置时应用可启动，讨论功能返回配置提示。注意：`build_settings` 必须逐键点路径合并（`set_settings(f"{ns}.{k}", v)`）——直接传 settings model 会整体替换 Agently 插件命名空间、丢失 path_mapping/content_mapping 默认值。测试默认使用模拟模型（传输边界注入），不依赖真实 API。

## 开发流程（强制）

Spec 驱动 + TDD，规则详见 `spec/README.md`：

1. 新功能先建 spec（从 `spec/templates/spec-template.md` 复制），按 `draft → designing → implementing → done` 用目录移动表达流转；放弃进 `archived`。文件名 `NNN-kebab-case-name.md`（NNN 三位递增）。
2. spec 进入 implementing 的前提：行为列表可测、验收标准分类（硬门=确定性测试/软标=语义质量）、测试映射完成。
3. implementing 中按行为列表垂直切片：一条行为 → 一个测试（先确认 RED）→ 最小实现（GREEN）→ 下一行为。禁止先写全部测试再写全部实现。测试走公共接口，仅模型调用与文件系统边界 mock。
4. 未进 implementing 不写实现；行为未全绿不算完成；全绿后迁入 done。
5. **每次变更必须同时**：在 `docs/timeline.md` **顶部**追加一行（`日期 ｜ 类型 ｜ 内容 ｜ 原因/依据`，类型限 `迁移/环境/规范/结构/选型/需求`，严格倒序；目录重组、规范变更、选型定稿、spec 回退必须留条目），并更新 `TO_DO.md` 的进行中与已完成清单；跨模块架构决策的完整推理记入 `docs/design-notes.md`。三者缺一视为变更未完成。
6. **文档分工**：`README.md` 只作入口（不写易过期计数）；产品说明 `docs/product-guide.md`；架构与三张图 `docs/architecture.md`（唯一图源，其他文档只链接不复制）；统计口径 `docs/statistics-methods.md`；评估基线 `docs/evaluation-report.md`。`backend/tests/test_docs_consistency.py` 守护「附录工具清单 == 注册表」「无死链」「README 无具体计数」「三图非空」。

## 架构

### Owner 划分（Agently 语义，必须遵守）

模型只拥有语义决策；schema 校验、枚举约束、算术与副作用归宿主代码。

- `ModelRequest`（经 `config.ModelGateway`）：单次模型交互与结构化输出契约（`.input/.info/.instruct/.output` 四段式，逐字段声明类型/语义/约束）；宿主用 pydantic 做校验权威
- `TriggerFlow`（`pipeline/workflow.py`）：应用层编排 `execute → review(pause_for 等待审阅) → route`；修正回边 `flow.when("RE_EXECUTE")` 图可见
- `LocalRecordStore`（Agently 原生）：执行记录（collection=executions）与会话记录（collection=sessions）按 `scope.session_id` 查询；put/get/search 均为 async
- `TaskContext`/`TaskWorkspace`：后续完整接线（当前上传文件与会话目录为轻量实现，见 docs/design-notes.md）

禁止反模式：自定义状态存储或重试管理器、关键词/正则做语义判断、未经消费的输出字段、全量数据塞 prompt（讨论只带 TableProfile 画像摘要）。

### 模块结构（backend/src/medsta/）

- `config.py`：ProviderConfig（自动加载项目根 .env）+ InterpretConfig（解释开关与句数上限，`from_env` 读取 `MEDSTA_INTERPRET*`）+ build_settings（逐键点路径合并 OpenAICompatible 配置，保留插件默认值）+ ModelGateway（request_structured，测试可注入 request_factory）
- `app.py`：create_app 工厂 + 模块级 app；挂载 routes_session/routes_data/routes_capabilities/routes_export/routes_report/routes_templates/ws 路由与 /data 静态目录（artifact 图表）；可选鉴权中间件（038 单令牌 / 044 多用户 `MEDSTA_USERS`，归属 404、直链 `?token=`、WS 4403）
- `api/`：REST（会话创建、删除〔DELETE：快照/事件流/产物一并清理〕、批量清理重复会话〔POST `/sessions/cleanup_duplicates`：按绑定文件名分组保留最新、未绑定/执行中跳过；鉴权中间件对这类集合级动作有白名单豁免〕、数据上传〔50MB + 行数上限 `MEDSTA_MAX_ROWS` 默认 20 万〕、列类型、能力目录、导出、报告 docx/pdf/md、模板、/auth/login〔常数时间比较 + 同 IP 60s 窗 5 次失败 429，内存计数〕）+ WebSocket `/ws/{session_id}` 薄封装（逻辑在 SessionService；出站帧经 EventLog 注入单调 seq）
- `session/persistence.py`（032）：SessionStore 快照（JSON + 原子写、启动恢复、executing 降级 discussing）
- `session/events.py`（035/036）：EventLog 事件流（events.jsonl 追加写 + 超阈值原子轮转保留尾部一半；`resume`+`last_seq` 缺口补发；用户动作帧 `*_user` 占 seq 不实时广播）
- `session/templates.py`（034）：工作链模板存取（data_root/templates/*.json）
- `reporting.py`（040）：报告中间表示（学术/轻量风格）→ docx/pdf/md 渲染，正交分层
- `session/manager.py`：会话状态机 `discussing → plan_confirmed → executing → delivered →（修正）→ discussing`（宿主确定性，非模型决策）；多工作区（datasets + active_dataset_id）
- `session/service.py`：消息编排（chat/confirm_plan/chart_choice/review/option/workspace/interrupt/resume/type_confirm/run_chain/plot_later/suggest_column_types）——讨论生成方案（流式）、确认后出图配置暂停（chart_config→chart_choice）、执行审阅交付或修正回讨论；修正意见注入再讨论；交付态 chat 转答疑（`answer`）、解释后台任务（步骤签名防串台，中断时取消）；043 输入守卫（宿主预筛零 token + 模型 off_topic 自检）；执行/出图配置期 chat 被 SESSION_BUSY 拒绝；执行经后台任务驱动（`_execute_plan` 同步登记句柄即返回、`_execution_task` 推进至审阅），计算期间 interrupt 实时处理；`resume` 按状态回放（review / delivered / executing 不降级）；异常路径统一 teardown 工作流句柄
- `agents/type_advisor.py`（041）：ColumnTypeAdvisor——模型只做列类型语义建议，宿主校验、用户敲定
- `agents/discussion.py`：DiscussionAgent + AnalysisPlan/PlanStep 契约（方法与图表枚举、宿主校验目标列 ⊆ 画像列名）；`MethodType` 必须等于注册表键 ∪ `ALIASES`，由 `tests/test_method_contract.py` 守护（漏改会让模型输出被 pydantic 直接拒绝）
- `agents/discussion.py`（029）：`EstimandSpec`/`IntercurrentEvent`（ICH E9(R1) 五要素）+ `sap_status_of(plan)` 纯函数；状态只有 `estimand_declared`/`exploratory`，**不得**写成 pre-specified 或确证性（由 `tests/test_estimand.py` 扫描前后端文案守护）
- `agents/interpretation.py`：InterpretationAgent（interpret/answer）——宿主证据白名单（按方法取结论键，不传原始数据）+ 模型只写句子；因果断言硬门（否定语境豁免）、未核验数值软标、句数截断；`build_evidence` 为唯一证据出口
- `data/parser.py`：CSV/xlsx 解析（不支持的扩展名抛 ValueError）
- `data/profiler.py`：变量类型四槽位（continuous 连续 / ordinal 数值-等级 / categorical 类别 / index 序列索引，统计默认排除）推断 + 七列统计口径（count/mean/median/q25/q75/min/max）；整数列按「测量指标列名（词元/中文子串）→ 连续，非负且跨度≤10 → 等级，其余宽范围计数 → 连续」判定，0/1 仍为等级；`apply_column_type` 支持用户修正（视为敲定）；TableProfile.type_confirmed 为讨论前置门控
- **前端语义约定**：会话 Tab=与 LLM 交互（讨论/方案/审阅操作摘要）；工作区 Tab=数据画像（类型可编辑下拉）、统计表交付（含 CSV/XLSX 导出）、图表；上传走工作区"+"直接导入
- `stats/registry.py`：**统计方法单一真相源**——ToolSpec（方法/必填槽位/task/applicability 适用条件/允许图表/实现）、`validate_step`/`validate_plan`（含 rationale 必填校验）、`execute_step`（兜底挂 `method_note`）、`tool_catalog`；新增方法只改注册表
- `stats/descriptive.py`（023）：`classify_distribution` 分布四态判定（insufficient/normal/log_normal/skewed）→ 推荐 x̄±s / M(P25~P75) / G；`descriptive_stats`（sd/CV/IQR/极差/众数/偏度/几何均数）；`reference_range`（正态法/百分位数法/对数正态法 × 90/95/99 × 单双侧）
- `stats/notes.py`（023）：`METHOD_NOTES` 教材口径文案单一源（章节与公式、适用条件、解读禁忌），随结果下发并在审阅卡折叠展示
- `stats/inference.py`（024/025）：`one_sample_test`（t/Wilcoxon + μ0 + 单双侧）、`randomized_block_anova`（SS 三分解）、`mcnemar_test`（配对四格表）、`factorial_anova`（两因素 + 交互，平衡正交分解 / 不平衡 Type II）、`repeated_measures_anova`（单因素组内，未做球形性校正）、`sample_size`（六种设计 × n/power，设计期工具，无目标列）
- `stats/significance.py`（024/025）：`snk_q_pvalue`（studentized range 动态 span）、`snk_step_down`（逐步规则）、`tukey_q_pvalue`（k 固定）、`lsd_t_pvalue`、`scheffe_pvalue`、`dunn_pvalue`、`bonferroni_alpha`
- 事后比较统一挂在 `anova.correction`（snk/tukey/dunnett/lsd/scheffe/holm/bonferroni），Dunnett 需 `control_group`；Kruskal 路径忽略参数事后退回 Dunn
- `stats/impute.py`（028）：`missing_pattern`（univariate/monotonic/arbitrary）、`mechanism_hint`（分组差异提示，不给判定）、`impute_mice`（m 次不同种子取均值 + 插补间方差）、`impute_simple`（median/mean/locf，仅敏感性）、`delta_scan`；产出 `imputed_step.csv` 供 service 注册数据集。依赖 `scikit-learn>=1.3`（必需），`IterativeImputer` 必须先 `from sklearn.experimental import enable_iterative_imputer`
- `stats/cleaning.py`（045）：数据清洗六工具——`dedupe`/`filter_rows`/`standardize`/`bin_column`/`outlier_report`/`winsorize`；数据产出型遵循 impute 同款约定（`cleaned_step_{i}.csv` + `_next_frame` 链间管道 + service 注册 dataset_added imputed=false）；`MethodType`/`METHOD_NOTES`/JSON 采样/附录 A/tools.md 均已同步（对应守护测试会拦漏改）
- `stats/survival.py`（027）：`km_estimate`（教材 §14-2 排序规则 + Greenwood SE + CI 截断 + 中位生存期取 KM 阶梯定义 S(t)≤0.5 的最小观测时间）、`logrank_test`（多组 g−1 维二次型，Breslow 以 n_i 加权）、`cox_fit`（PHReg + 手建零模型算 LR + Schoenfeld）、`rmst`（梯形积分）；竞争风险与 Fine–Gray 标 planned
- `ChartType` 必须等于 `CHART_TYPES`，由 `tests/test_method_contract.py` 守护（与 `MethodType` 同理）
- `stats/methods.py`：12 类确定性实现；检验策略链（正态性→Levene→失衡→最优/次优；卡方期望频数→Fisher 降级）输出 `strategy{steps[],final_method,alternative}`；anova ≥3 组输出 overall+pairwise（Holm/Bonferroni 校正）+ 多重性提醒
- `stats/significance.py`：significance_label（α 判定+星号）、p_adjust（holm/bonferroni）
- `stats/plotting.py`：CJK 字体检测与英文回退、12 类图表渲染（含 pie、survival_curve、显著性比较线标注）、render_combined 拼图
- `pipeline/executor.py`：注册表派发 + 计划级硬校验（失败抛 ToolValidationError）+ 单步失败隔离（failed + error.code）+ `on_step` 进度回调 → ExecutionReport
- `errors.py`：16 个错误码（含 `PROTOCOL_UNSUPPORTED`、`NO_ACTIVE_RUN`、`SESSION_BUSY`）+ `AppError.to_event()`（WS `{type:error,code,message,hint,detail}`）
- `pipeline/workflow.py`：AnalysisWorkflow（TriggerFlow），create（同步建执行句柄，供中断/清理先行登记）/ start（阻塞至流程首个暂停点）/ run=create+start 兼容入口 / wait_for_review / review / cancel。执行由 `SessionService._execution_task` 后台驱动，句柄关闭放被取消任务的 CancelledError 路径（Agently `async_close` 会 drain 计算线程，不得在 WS 收包循环中等待）

前端 `frontend/src/`：`App.tsx` 双栏工作台（左会话流/右数据图表工作区 + 工具装配 Tab，窄屏切 Tab；事件 phase/messages 按 session 落地，交互卡 active-only；恢复会话首连 resume 回放）；`api/client.ts` REST+WS 封装（含 withToken 直链、createSession 抛错）；`chat/`（方案卡、出图配置卡 chartOptions.ts、审阅卡、答疑卡）；`workspace/`（画像表格、图表卡片、结果表格、报告导出）；`builder/`（run_chain 装配器、模板）；`hooks/useFileDrop`（拖拽导入）；ErrorBoundary、`UploadChoiceDialog`（046 已绑定会话再上传的数据去向选择）、`SessionTabs`（标签「×」删除会话，onDelete 可选）与登录卡。开发期用 Vite proxy，无需处理跨域。

### 测试架构（spec 019）

- 四层金字塔：方法层（`stats`/`profiler`/`plotting`）→ 编排层（`SessionService`/`AnalysisWorkflow`，注入假模型）→ 契约层（TestClient REST + WebSocket）→ 前端层（Vitest + RTL，仅 mock `fetch`/`WebSocket`）+ Playwright（`backend/tests/e2e_app.py` 桩模型后端）。
- 测试隔离：`backend/tests/conftest.py` 提供 `data_root`/`app`/`client`/`session_id`/`sample_df` 与自动清场；`create_app(data_root=...)` 注入 `app.state.data_root`，`SessionManager.clear()` 清场。**测试不得写真实 `backend/data`，也不得依赖 `.env`——这是机制而非约定**：conftest 的 autouse 夹具 `_no_real_gateway` 强制 app 工厂内 `build_gateway` 抛错（补丁源模块 `medsta.config`，拦截 `_build_service` 的函数局部导入），真实模型冒烟（`real_llm` marker，`MEDSTA_REAL_LLM=1`）显式豁免。要交付态答疑的测试注入替身解释器（见 `test_qa_flow`）；要交付态出新方案的测试可显式 `set_interpret_agent(None)` 表达意图（见 `test_export_chart_formats`）。`medsta.app` 的模块级 `app` 为 PEP 562 惰性构建——导入该模块无副作用，`uvicorn medsta.app:app` 首次取属性时构建。
- 真模型用例只放 `tests/test_real_llm_smoke.py`，`MEDSTA_REAL_LLM=1` 才运行（已注册 `real_llm` marker），默认 skip。
- CI：`.github/workflows/ci.yml` 三作业（backend 含 ruff+mypy+pytest、frontend、e2e），与 `scripts/ci.sh` 互为镜像；后端 `pytest-cov` 门槛 83%（调整时同步 `scripts/ci.sh` 的 `COVERAGE_MIN`）；E2E 安装 `fonts-noto-cjk` 并缓存 Chromium；分支保护需在 GitHub 后台手动开启。测试若疑似卡死，用 `pytest -o faulthandler_timeout=60` 转储线程栈定位。
- 评估基线：`docs/evaluation-report.md`（G0–G7 门禁与决策板 A–D 差距矩阵、P0/P1/P2 建议）。

### 共同契约

`AnalysisPlan`（chat 下发 plan 事件）、WS 消息契约（`spec/done/006-session-api.md`）与 ExecutionReport 是前后端与测试的共同契约，改动需同步更新契约测试与前端 `types.ts`。

结果解释相关（022）：`interpretation` 事件在 `review_request` 之后异步推送（失败静默不推 error），`answer` 事件仅在 `delivered` 态回答 chat；该态下 `chat` 不产 plan、`review revise` 回讨论。开关 `MEDSTA_INTERPRET=0`，句数 `MEDSTA_INTERPRET_MAX_SENTENCES`（默认 1，clamp 1–5）。

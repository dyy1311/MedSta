# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

MedSta：面向数据研究者的轻量级 AI 数据统计分析/预测/绘图及解释智能体（Web 端）。上传数据 → 解析画像 → ReAct 讨论生成结构化分析方案 → 确认后 Pipeline 执行 → 交付图表与解释建议 → 可修正再执行。

## 常用命令

```bash
# 环境（用户使用 mamba，环境名 Sta；shell 未初始化时先 eval "$(mamba shell hook --shell bash)"）
mamba activate Sta

# 后端依赖安装（pip 直连困难时加 -i https://pypi.tuna.tsinghua.edu.cn/simple）
cd backend && pip install -e ".[dev]"

# 运行全部后端测试（当前 200 collected：199 passed + 1 项真模型 skip）
cd backend && pytest

# 运行单个测试
cd backend && pytest tests/test_pipeline.py -k "test_forecast_step"

# 真实模型冒烟（显式开启，消耗额度；默认 skip）
cd backend && MEDSTA_REAL_LLM=1 pytest tests/test_real_llm_smoke.py -q

# 一键启动（项目根，dev 模式：后端 8000 + 前端 5173，Ctrl+C 整组退出）
cd /home/xdy/MedSta && python main.py

# prod 模式（构建前端后由 8000 单端口托管 SPA+API；app.py 按 frontend/dist 存在性自动启用托管）
cd /home/xdy/MedSta && python main.py --prod

# 启动后端（http://localhost:8000，/health 健康检查）
cd backend && uvicorn medsta.app:app --reload --port 8000

# 前端（Vite 5 + React 18 + TS + Tailwind 3，dev 端口 5173，已代理 /sessions /data /ws 到 8000）
cd frontend && npm install
cd frontend && npm run dev      # 开发
cd frontend && npm run build    # 构建（tsc -b && vite build）
cd frontend && npm run lint     # ESLint
cd frontend && npm test         # Vitest + Testing Library（jsdom，仅 mock fetch/WebSocket）
cd frontend && npm run test:coverage
cd frontend && npm run test:e2e # Playwright（自动起 8021 桩后端 + 5174 Vite）

# 本地 CI 镜像（等价 .github/workflows/ci.yml：后端 pytest+覆盖率门槛、前端 lint/build/vitest、E2E）
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
5. **每次变更必须同时**：在 `docs/timeline.md` 追加一行（日期/事项/动作/说明），并更新 `TO_DO.md` 的进行中与已完成清单；跨模块架构决策记入 `docs/design-notes.md`。三者缺一视为变更未完成。

## 架构

### Owner 划分（Agently 语义，必须遵守）

模型只拥有语义决策；schema 校验、枚举约束、算术与副作用归宿主代码。

- `ModelRequest`（经 `config.ModelGateway`）：单次模型交互与结构化输出契约（`.input/.info/.instruct/.output` 四段式，逐字段声明类型/语义/约束）；宿主用 pydantic 做校验权威
- `TriggerFlow`（`pipeline/workflow.py`）：应用层编排 `execute → review(pause_for 等待审阅) → route`；修正回边 `flow.when("RE_EXECUTE")` 图可见
- `LocalRecordStore`（Agently 原生）：执行记录（collection=executions）与会话记录（collection=sessions）按 `scope.session_id` 查询；put/get/search 均为 async
- `TaskContext`/`TaskWorkspace`：后续完整接线（当前上传文件与会话目录为轻量实现，见 docs/design-notes.md）

禁止反模式：自定义状态存储或重试管理器、关键词/正则做语义判断、未经消费的输出字段、全量数据塞 prompt（讨论只带 TableProfile 画像摘要）。

### 模块结构（backend/src/medsta/）

- `config.py`：ProviderConfig（自动加载项目根 .env）+ build_settings（逐键点路径合并 OpenAICompatible 配置，保留插件默认值）+ ModelGateway（request_structured，测试可注入 request_factory）
- `app.py`：create_app 工厂 + 模块级 app；挂载 routes_session/routes_data/ws 路由与 /data 静态目录（artifact 图表）
- `api/`：REST（会话创建、数据上传）+ WebSocket `/ws/{session_id}` 薄封装（逻辑在 SessionService）
- `session/manager.py`：会话状态机 `discussing → plan_confirmed → executing → delivered →（修正）→ discussing`（宿主确定性，非模型决策）；多工作区（datasets + active_dataset_id）
- `session/service.py`：消息编排（chat/confirm_plan/chart_choice/review/option/workspace/interrupt/resume）——讨论生成方案（流式）、确认后出图配置暂停（chart_config→chart_choice）、执行审阅交付或修正回讨论；修正意见注入再讨论
- `agents/discussion.py`：DiscussionAgent + AnalysisPlan/PlanStep 契约（方法与图表枚举、宿主校验目标列 ⊆ 画像列名）
- `data/parser.py`：CSV/xlsx 解析（不支持的扩展名抛 ValueError）
- `data/profiler.py`：变量类型四槽位（continuous 连续 / ordinal 数值-等级 / categorical 类别 / index 序列索引，统计默认排除）推断 + 七列统计口径（count/mean/median/q25/q75/min/max）；整数列按「测量指标列名（词元/中文子串）→ 连续，非负且跨度≤10 → 等级，其余宽范围计数 → 连续」判定，0/1 仍为等级；`apply_column_type` 支持用户修正（视为敲定）；TableProfile.type_confirmed 为讨论前置门控
- **前端语义约定**：会话 Tab=与 LLM 交互（讨论/方案/审阅操作摘要）；工作区 Tab=数据画像（类型可编辑下拉）、统计表交付（含 CSV/XLSX 导出）、图表；上传走工作区"+"直接导入
- `stats/registry.py`：**统计方法单一真相源**——ToolSpec（方法/必填槽位/task/applicability 适用条件/允许图表/实现）、`validate_step`/`validate_plan`（含 rationale 必填校验）、`execute_step`、`tool_catalog`；新增方法只改注册表
- `stats/methods.py`：12 类确定性实现；检验策略链（正态性→Levene→失衡→最优/次优；卡方期望频数→Fisher 降级）输出 `strategy{steps[],final_method,alternative}`；anova ≥3 组输出 overall+pairwise（Holm/Bonferroni 校正）+ 多重性提醒
- `stats/significance.py`：significance_label（α 判定+星号）、p_adjust（holm/bonferroni）
- `stats/plotting.py`：CJK 字体检测与英文回退、11 类图表渲染（含 pie、显著性比较线标注）、render_combined 拼图
- `pipeline/executor.py`：注册表派发 + 计划级硬校验（失败抛 ToolValidationError）+ 单步失败隔离（failed + error.code）+ `on_step` 进度回调 → ExecutionReport
- `errors.py`：15 个错误码（含 `PROTOCOL_UNSUPPORTED` 协议错误、`NO_ACTIVE_RUN`）+ `AppError.to_event()`（WS `{type:error,code,message,hint,detail}`）
- `pipeline/workflow.py`：AnalysisWorkflow（TriggerFlow），run/wait_for_review/review/cancel

前端 `frontend/src/`：`App.tsx` 双栏工作台（左会话流/右数据图表工作区，窄屏切 Tab）；`api/client.ts` REST+WS 封装；`chat/`（上传区、方案卡片、审阅卡片）；`workspace/`（画像表格、图表卡片）。开发期用 Vite proxy，无需处理跨域。

### 测试架构（spec 019）

- 四层金字塔：方法层（`stats`/`profiler`/`plotting`）→ 编排层（`SessionService`/`AnalysisWorkflow`，注入假模型）→ 契约层（TestClient REST + WebSocket）→ 前端层（Vitest + RTL，仅 mock `fetch`/`WebSocket`）+ Playwright（`backend/tests/e2e_app.py` 桩模型后端）。
- 测试隔离：`backend/tests/conftest.py` 提供 `data_root`/`app`/`client`/`session_id`/`sample_df` 与自动清场；`create_app(data_root=...)` 注入 `app.state.data_root`，`SessionManager.clear()` 清场。**测试不得写真实 `backend/data`，也不得依赖 `.env`。**
- 真模型用例只放 `tests/test_real_llm_smoke.py`，`MEDSTA_REAL_LLM=1` 才运行（已注册 `real_llm` marker），默认 skip。
- CI：`.github/workflows/ci.yml` 三作业（backend/frontend/e2e）；后端 `pytest-cov` 门槛 83%（2026-10-21 实测 88.19% −5pt，调整时同步 `scripts/ci.sh` 的 `COVERAGE_MIN`）；E2E 安装 `fonts-noto-cjk` 并缓存 Chromium；分支保护需在 GitHub 后台手动开启。
- 评估基线：`docs/evaluation-report.md`（G0–G7 门禁与决策板 A–D 差距矩阵、P0/P1/P2 建议）。

### 共同契约

`AnalysisPlan`（chat 下发 plan 事件）、WS 消息契约（`spec/done/006-session-api.md`）与 ExecutionReport 是前后端与测试的共同契约，改动需同步更新契约测试与前端 `types.ts`。

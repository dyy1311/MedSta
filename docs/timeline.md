# MedSta 开发时间线

> 按日期倒序或正序追加均可，但每次 spec 流转 / 里程碑必须记录一行。格式：`日期 | spec/事项 | 动作 | 说明`。

| 日期 | Spec / 事项 | 动作 | 说明 |
|---|---|---|---|
| 2026-10-17 | — | 项目立项 | 确定选型：Agently + FastAPI + React SPA + mamba（Sta 环境）；spec 生命周期定为 draft/designing/implementing/done/archived |
| 2026-10-17 | — | 治理基座 | 建立 spec/ 目录与模板、docs 画像/设计思路、CODEBUDDY.md、README |
| 2026-10-17 | 001 后端骨架 | implementing | mamba Sta 环境 + pytest 就绪；TDD B1–B5 全绿（健康检查、会话创建、Agently OpenAICompatible provider 配置、模拟模型结构化契约）。pip 走清华镜像 |
| 2026-10-17 | 002 数据解析与画像 | implementing | B1–B6 全绿：CSV/xlsx 解析、类型推断、缺失/数值/类别画像、TableProfile JSON 序列化 |
| 2026-10-17 | 003 讨论智能体 | implementing | B1–B5 全绿：AnalysisPlan 契约（方法/图表枚举、宿主列名校验）、画像注入 info、revision_note 注入 instruct；模拟模型传输边界测试 |
| 2026-10-17 | 004 pipeline 引擎 | implementing | B1–B8 全绿：describe/correlation/regression/forecast/t 检验五类步骤 + 六类图表 PNG artifact + ExecutionReport 序列化；matplotlib Agg 后端 |
| 2026-10-17 | 005 分析工作流 | implementing | B1–B4 全绿：TriggerFlow 编排（review pause_for 等待审阅、RE_EXECUTE 图可见回边）、LocalRecordStore 执行记录按 session_id 查询 |
| 2026-10-17 | 006 会话编排 API | implementing | B1–B6 全绿：REST 上传+画像、SessionService 编排（chat/confirm/review）、WS 薄封装、RecordStore 会话记录；修正意见注入再讨论 |
| 2026-10-17 | 007 前端 SPA | implementing→done | Vite5+React18+TS+Tailwind3 双栏工作台（聊天流/数据图表工作区、方案卡、审阅卡、图表放大下载）；npm run build 通过 |
| 2026-10-17 | 001–006 | implementing → done | 后端 34 项测试全绿；端到端冒烟通过（建会话→上传→画像→WS 讨论链路）；uvicorn/前端 dev 启动验证 |
| 2026-10-17 | 007 真实模型验证与 config 修复 | done | 冒烟发现并修复三缺陷：.env 未自动加载（from_env 加 load_dotenv）、timeout 缺 write/pool（httpx 报错）、set_settings(model) 整体替换插件命名空间丢默认值（改逐键点路径合并）；另修 executor artifact 返回完整路径→改文件名（前端 URL 拼接）。37 项测试全绿；DeepSeek deepseek-flash 真实模型端到端闭环通过（讨论→3 步方案→执行→3 图表 URL 200→交付） |
| 2026-10-17 | 008 一键启动器 | done | 项目根 `python main.py`（dev 双子进程，进程组管理含 npm→vite 整树终止、日志前缀透传、Ctrl+C 整组退出）；`--prod` 构建后 FastAPI 单端口托管 SPA（catch-all 豁免 API 前缀）；45 项测试全绿，dev/prod 双模式真实冒烟通过 |
| 2026-10-19 | 018 会话×工作区绑定 | done | 会话 Tab 条（显示绑定表格名/新建会话/自动绑定）；新建工作区自动新建绑定会话；消息按会话隔离；修复事件路由 stale closure（思考折叠生效）；ws 破图占位；artifact 404 根因为 8000 端口后端旧进程未重启（已提示）。102 测试全绿 + 构建通过 |
| 2026-10-19 | 015–017 类型系统/前置确认/工作区语义 | done | 修复工作区+导入；四类变量类型（continuous/ordinal/categorical/index）推断+画像下拉编辑+PATCH 端点；type_review 前置节点（chat 拦截+自动继续+生成失败带反馈重试）；类型驱动方法/图表映射（accepts 校验/ordinal 降级/index 排除）；统计口径七列（均值/中位数/q25/q75/min/max/计数，类别频数表）；会话/工作区语义重构（表格交付进工作区+导出、ReviewCard 摘要化）；plot_suggest/plot_later 补绘图；ws 并发发送加锁。前端构建通过 + 真实模型端到端（类型确认→3 步方案→交付→导出 200） |
| 2026-10-19 | 012–014 多工作区/槽位化/出图确认 | done | 能力披露修复（vite proxy）；多工作区分页（多表格独立工作区+激活切换）；工具槽位化（task/slots/applicability + rationale 强制）；检验策略链（正态性→Levene→失衡→最优/次优；卡方期望频数→Fisher 降级）；显著性规范（α 讨论/星号/Holm 校正/多重提醒/图中标注）；出图前确认（chart_config/chart_choice，图表类型+拼图）；可视化表格交付 + CSV/XLSX 导出；思考折叠。90 项测试全绿 + 真实模型端到端（4 步方案→出图确认→拼图→导出 200） |
| 2026-10-18 | 009 统计工具库 | done | 修复 hypothesis_test 缺参 KeyError：建立 ToolSpec 单一真相源（参数契约/图表声明/实现），10 类方法（describe/missing_report/normality_test/group_compare/anova/chi_square/correlation/regression/logistic_regression/timeseries_forecast）+ 11 类图表；executor 注册表派发、单步失败隔离；中文字体配置（Noto CJK）+ 英文回退。60 项测试全绿 |
| 2026-10-18 | 010 实时交互 | done | 错误码体系（12 码）+ WS 错误事件；ModelGateway 单请求流式（SSE + 结构化结果）；会话任务化、中断/继续、执行步骤进度；单步失败隔离。真实冒烟：流式 7296 字符、中断成功 |
| 2026-10-18 | 011 选项与能力披露 | done | AnalysisPlan.options（宿主保证 confirm/唯一/≤4）；工具目录注入 info；GET /capabilities（方法+参数+图表+planned）；WS option 路由；前端能力抽屉/选项按钮/自定义补充输入/流式气泡/中断按钮/错误卡；npm build 通过 |
| 2026-10-18 | 009–011 端到端验证 | done | 真实模型：分组比较+相关分析方案（4 选项）→ 进度 1/2、2/2 → 2 张图表交付；图表无缺字告警；74 项测试全绿 |
| 2026-10-17 | — | 待办 | WebSocket 断线重连；多会话历史回放；结果解释功能（模型生成文字解读，当前仅图表+数据） |
| 2026-10-21 | 021 CI 流水线 | implementing → done | git init + 首次提交 `316b103` 推送 main；GitHub Actions 三作业（backend 覆盖率 88.19%/门槛 83%、frontend、e2e 装 fonts-noto-cjk + 缓存 Chromium）；本地 `scripts/ci.sh` 全量通过，负向校验 `COVERAGE_MIN=99` 退出码 1 且立即中断；首次 Actions run `39571533398` 三作业 success；分支保护待 GitHub 后台手动开启 |
| 2026-10-21 | 020 正确性护栏 | implementing → done | 整数测量变量按列名词元/中文子串 + 跨度规则判 continuous（年龄/血压），0/1 与评分分级保持 ordinal；Logistic 三重分离检测（未收敛 / max\|β\|≥15 / OR 非有限）拒绝输出并给出 Firth 建议，替换准分离测试夹具；新增 `PROTOCOL_UNSUPPORTED`；类型确认卡「数值列全部设为连续」；后端 200 collected、前端 35 passed、E2E 2 passed |
| 2026-10-21 | 019 全链路测试体系 | implementing → done | 四层测试金字塔（后端 195 collected / 前端 34 / E2E 2；前端覆盖率 88.61%）；测试隔离改造（数据根请求期解析 + app.state 注入 + manager.clear + conftest）；修复 10 类缺陷（工作区报告不可见、delivered 不更新卡片、上传错误静默、WS 类型未校验、未知会话崩溃、空文件 500、BOM 污染、pie 未披露、group_compare >2 组静默丢弃、数据根未隔离）；产出 `docs/evaluation-report.md`（G0–G7 与决策板 A–D 差距矩阵 + P0/P1/P2 建议） |

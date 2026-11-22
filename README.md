# MedSta

[![CI](https://github.com/dyy1311/MedSta/actions/workflows/ci.yml/badge.svg)](https://github.com/dyy1311/MedSta/actions/workflows/ci.yml)

面向数据研究者的轻量级 AI 赋能数据分析智能体（Web 端）。上传数据后，系统解析并生成数据画像，
以对话方式与你讨论形成分析方案，经你确认后由**确定性统计引擎**执行，交付统计表、图表与受控解读；
用户可提出修正意见再执行，最终交付成果。

> 模型只负责理解意图与撰写解读；**所有数值由宿主代码计算**，同一份数据必得同样的结果。

## 快速开始

```bash
# 1. 激活环境
mamba activate Sta

# 2. 安装依赖
cd backend && pip install -e ".[dev]"
cd ../frontend && npm install && cd ..

# 3. 配置模型服务（OpenAI 兼容接口）
cp .env.example .env   # 填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
# 可选：设置 MEDSTA_AUTH_TOKEN 开启访问令牌鉴权（HTTP 头 X-Auth-Token；WS ?token=；/health 豁免）

# 4. 一键启动（dev：后端 8000 + 前端 5173）
python main.py

# 或 prod 模式（构建前端后由 8000 单端口托管）
python main.py --prod
```

也可分别启动：后端 `cd backend && uvicorn medsta.app:app --reload --port 8000`；前端 `cd frontend && npm run dev`。

## 文档导航

| 文档 | 读它了解什么 |
|---|---|
| [产品说明](docs/product-guide.md) | 定位、目标用户、能力矩阵、交互旅程、交付物与边界 |
| [产品与实现讲解手册](docs/handbook.md) | 教学版全链路：心智模型、前后端调用链、Agent 编排、契约速查、动手实验与排错 |
| [系统架构与统计流程](docs/architecture.md) | 三张图：分层架构、统计策略选择、执行流程；工具清单与事件/状态对照 |
| [统计说明](docs/statistics-methods.md) | 每个方法的检验策略链、教材口径、外部标准与解读禁忌 |
| [评估基线](docs/evaluation-report.md) | 评分、测试资产、已修缺陷、剩余缺口与下一步 |
| [设计决策](docs/design-notes.md) | 关键取舍与踩过的坑（为什么这么设计） |
| [开发时间线](docs/timeline.md) | 每次结构性/策略性调整的决策记录 |
| [Spec 流程](spec/README.md) | spec 驱动 + TDD 的生命周期与模板 |

## 测试与 CI

```bash
# 后端（默认模拟模型，不依赖 .env / 网络）
cd backend && pytest

# 前端组件/布局/交互
cd frontend && npm test

# 浏览器全流程（自动拉起桩后端与 Vite）
cd frontend && npm run test:e2e

# 本地等价 CI（后端 + 前端 + E2E）
bash scripts/ci.sh

# 清理测试/手工操作留下的会话（服务在线走 API 删内存+磁盘，否则直接删目录）
python scripts/clean_sessions.py
```

推送 `main` 或提交 PR 时，GitHub Actions 自动运行后端（含覆盖率门槛）、前端、E2E 三个作业。
分支保护（CI 必过才能合并）需在仓库 Settings → Branches 手动开启。
当前用例数与覆盖率见 [评估基线](docs/evaluation-report.md)。

## 开发流程（spec 驱动 + TDD）

1. 在 `spec/draft/` 起草功能 spec，评审后移入 `spec/designing/` 细化
2. spec 敲定后移入 `spec/implementing/`，按行为列表逐条 RED-GREEN 写测试与实现
3. 全部行为测试通过后迁入 `spec/done/`
4. 每次功能流转在 `docs/timeline.md` 追加记录

详细规范见 [spec/README.md](spec/README.md)。

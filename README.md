# MedSta

[![CI](https://github.com/dyy1311/MedSta/actions/workflows/ci.yml/badge.svg)](https://github.com/dyy1311/MedSta/actions/workflows/ci.yml)

面向数据研究者的轻量级 AI 赋能数据分析智能体（Web 端）。用户上传数据（CSV/Excel）后，系统解析整理数据画像，以 ReAct 方式与用户讨论形成分析方案（统计分析/预测/绘图），方案确定后以 pipeline 执行，交付图表与解释建议；用户可修正方案并再次执行，最终交付成果。

## 统计能力（方法学依据见 `docs/statistics-methods.md`）

- 描述与质检：描述性统计（可分组/饼图）、缺失数据报告、正态性检验、方差齐性检验（Levene）、分组聚合表
- 组间比较：两组（正态性→方差齐性→t/Welch/Mann-Whitney 策略链 + Cohen's d）、多组（ANOVA/Kruskal + 两两比较 Holm 校正）、卡方（期望频数分析，2×2 自动 Fisher）
- 关联与预测：Pearson/Spearman 相关、线性回归、Logistic 回归（OR/AUC）、时间序列趋势预测
- 图表：直方图、箱线图、小提琴图、散点图、折线图、柱状图、分组柱状图、饼图、热力图、Q-Q 图、残差图；多图可拼同画板
- 变量类型：每列可标注为 数值-连续型 / 数值-等级型 / 类别型 / 序列索引（下拉编辑）；讨论前强制敲定，方法与图表按类型自动映射
- 交互：多工作区分页（多表格独立分析）、出图前确认图表类型/画板/α/校正方式、方案选项式确认、流式输出（思考可折叠）、中断/继续、错误分类可见、选择依据显式化（rationale + 策略链）、可视化表格交付 + CSV/Excel 导出

## 技术栈

- 后端：Python（mamba 环境 `Sta`）+ FastAPI（REST + WebSocket）+ Agently（OpenAI 兼容接口）
- 数据分析：pandas / statsmodels / scipy / matplotlib
- 前端：React + TypeScript + Vite + Tailwind CSS
- 测试：pytest（后端 200 项）+ Vitest/Testing Library（前端 35 项）+ Playwright（浏览器 E2E 2 项）

## 快速开始

```bash
# 1. 激活环境
mamba activate Sta

# 2. 安装后端依赖与前端依赖
cd backend && pip install -e ".[dev]"
cd ../frontend && npm install && cd ..

# 3. 配置模型服务（OpenAI 兼容接口）
cp .env.example .env   # 填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

# 4. 一键启动（dev：后端 8000 + 前端 5173，Ctrl+C 一键退出）
python main.py

# 或 prod 模式（构建前端后由 8000 单端口托管全部）
python main.py --prod
```

也可以分别启动：后端 `cd backend && uvicorn medsta.app:app --reload --port 8000`；前端 `cd frontend && npm run dev`。

## 持续集成

推送 `main` 或提交 PR 时，GitHub Actions 自动运行三个作业：后端 pytest（覆盖率门槛 83%）、
前端 lint/build/vitest、Playwright E2E（安装 CJK 字体）。失败时上传覆盖率与 Playwright trace。
配置见 `.github/workflows/ci.yml`。

本地等价检查（无需远端）：

```bash
bash scripts/ci.sh                  # 全量：后端 + 前端 + E2E
CI_SKIP_E2E=1 bash scripts/ci.sh    # 跳过浏览器端
```

分支保护（CI 必过才能合并）需在 GitHub 仓库 Settings → Branches 中手动开启。

## 测试

```bash
# 后端（默认模拟模型，不依赖 .env / 网络）
cd backend && pytest

# 真实模型冒烟（显式开启，消耗额度）
cd backend && MEDSTA_REAL_LLM=1 pytest tests/test_real_llm_smoke.py -q

# 前端组件/布局/交互
cd frontend && npm test
cd frontend && npm run test:coverage

# 浏览器全流程（自动拉起桩后端 8021 + Vite 5174）
cd frontend && npm run test:e2e
```

评估结论与改进建议见 `docs/evaluation-report.md`。

## 开发流程（spec 驱动 + TDD）

1. 在 `spec/draft/` 起草功能 spec，评审后移入 `spec/designing/` 细化
2. spec 敲定后移入 `spec/implementing/`，按 spec 行为列表逐条 RED-GREEN 写测试与实现
3. 全部行为测试通过后，spec 迁入 `spec/done/`；放弃的功能迁入 `spec/archived/`
4. 每次功能流转在 `docs/timeline.md` 追加记录

详细规范见 `spec/README.md`。

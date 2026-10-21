# 021 - CI 流水线接入

> 状态：implementing
> 创建：2026-10-21 ｜ 敲定：2026-10-21 ｜ 完成：—

## 背景与目标

spec 019 建立了 231 项自动化测试，spec 020 增加了正确性护栏，但这些检查目前只能靠人工记得执行。
本 spec 把它们固化为可重复运行的流水线：代码推送到 GitHub 后自动完成后端、前端与浏览器端验证，
失败即阻断，并保留排障证据。

## 范围

- 做：`git init` 与首次提交、根忽略补全、GitHub Actions 三作业（backend/frontend/e2e）、
  本地镜像 `scripts/ci.sh`、后端覆盖率门槛（实测 −5pt）、推送 main、核对 Actions 结果、文档同步。
- 不做：分支保护配置（GitHub 后台手动）、真实模型接入 CI（无密钥且消耗额度）、
  CD/部署、性能测试、依赖版本锁定。

## 行为列表（TDD 循环队列）

- [ ] B1: 首次提交只包含源码/配置/文档；`.env`、`backend/data/`、`node_modules/`、`frontend/dist/`、`coverage/`、`test-results/` 均未入库
- [ ] B2: `scripts/ci.sh` 依次执行后端 pytest、前端 lint/build/vitest、E2E；任一步失败立即以非零码退出
- [ ] B3: `CI_SKIP_E2E=1` 时脚本跳过 E2E，其余步骤照常执行
- [ ] B4: `.github/workflows/ci.yml` 可被 PyYAML 解析，含 `backend`/`frontend`/`e2e` 三个 job，触发 push(main)/pull_request/workflow_dispatch，同分支并发取消
- [ ] B5: `backend` job 以 `--cov-fail-under=<门槛>` 运行 pytest，门槛 = 本地实测语句覆盖率向下取整后减 5
- [ ] B6: `e2e` job 安装 `fonts-noto-cjk` 与 Chromium 后运行 `npm run test:e2e`，失败上传 `playwright-report`/`test-results`
- [ ] B7: `git push -u origin main` 成功后，远端 main 指向本地提交；Actions 首次运行结论可查询并记录

## 验收标准

- [硬门] B1–B6 通过；`bash scripts/ci.sh` 退出码 0（后端 199 passed + 1 skip、前端 35 passed、E2E 2 passed）。
- [硬门] workflow YAML 解析通过且三 job 结构完整；job 均设置 `timeout-minutes`。
- [硬门] 首次提交不含密钥与运行时数据；`.codebuddy/` 未被删除。
- [硬门] push 成功，`git ls-remote` 的 main 与本地 HEAD 一致。
- [软标] GitHub Actions 首次运行 success；若因环境差异失败，按日志修复后重推。
- [说明] 分支保护（CI 必过）需在 GitHub 仓库设置中手动开启，脚本无法代劳。

## 契约与测试映射

本 spec 不新增业务接口；「测试」是脚本与配置的可执行校验：

| 行为 | 公共接口 | 验证方式 |
|---|---|---|
| B1 | `git ls-files` | `git ls-files | grep -E '\.env$\|^backend/data/\|node_modules/'` 无输出 |
| B2 | `scripts/ci.sh` | `bash scripts/ci.sh` 退出码 0；临时制造失败命令验证非零透传 |
| B3 | `scripts/ci.sh` + env | `CI_SKIP_E2E=1 bash scripts/ci.sh` 输出跳过提示且不启动 Playwright |
| B4 | workflow YAML | `python -c "import yaml; ..."` 断言 jobs/触发/并发 |
| B5 | workflow `backend` job | 断言含 `--cov-fail-under=<门槛>` 且门槛值来自实测 |
| B6 | workflow `e2e` job | 断言含 `fonts-noto-cjk`、`playwright install`、artifact 上传 |
| B7 | git remote / GitHub API | `git ls-remote --heads origin main` 对比 `git rev-parse HEAD`；轮询 `actions/runs` |

## 依赖与影响

- `backend/pyproject.toml`：dev extras 增加 `pytest-cov`（仅测试依赖，不影响运行时）。
- `.gitignore`：补 `coverage/`、`playwright-report/`、`test-results/`、`blob-report/`。
- 远端：`https://github.com/dyy1311/MedSta.git`（空仓库，首次推送建立 main）。
- 影响：首次提交后仓库体积受控；CI 分钟数由 E2E 的 2 条串行用例决定。

## 备注

- 三作业并行是为了失败定位与总时长；E2E 需要 Python+Node 双环境，独立成 job。
- E2E 安装 CJK 字体是为了覆盖真实中文图表路径；不装时英文回退也应通过，但会失去该路径验证。
- 覆盖率门槛只防大幅倒退，不追求数字；前端沿用 v8 报告，暂不设硬阈值。

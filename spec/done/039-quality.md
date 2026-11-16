# 039 - 工程质量收尾（logging / ruff / mypy / 错误边界）

> 状态：done
> 创建：2026-11-17 ｜ 敲定：2026-11-17 ｜ 完成：2026-11-17
> 上游：审查遗留工程质量项

## 范围

- 做：
  - `print` → `logging`（各模块 `logger = getLogger(__name__)`，保留原信息粒度）；守护测试断言 src 无 `print(`
  - ruff：pyproject `[tool.ruff]`（line-length 100，E/F/W/I/UP）+ `ruff check` 零告警（含 `--fix` 存量修复）；scripts/ci.sh 后端作业追加
  - mypy：宽松配置（`ignore_missing_imports`，非 strict）对 `src/medsta` 通过；ci.sh 追加
  - 前端 ErrorBoundary：class 组件 + fallback（reload 按钮）；App 外层包裹；组件测试
- 不做（YAGNI）：严格 mypy（disallow_untyped_defs 等，另行）、结构化日志、前端监控上报

## 行为列表

- [x] B1: `src/medsta/**/*.py` 无 `print(` 调用（守护测试），行为不变（全量回归）
- [x] B2: `ruff check src/medsta tests` 零告警；ci.sh 后端作业含该步
- [x] B3: `mypy src/medsta` 宽松配置零报错；ci.sh 含该步
- [x] B4: 前端子组件渲染抛错时 ErrorBoundary 显示 fallback 与重载按钮

## 测试映射

| 行为 | 测试 |
|---|---|
| B1 | `tests/test_no_print_statements.py` |
| B2/B3 | ci.sh 步骤（命令退出码） |
| B4 | `src/components/ErrorBoundary.test.tsx` |

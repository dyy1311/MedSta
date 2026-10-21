#!/usr/bin/env bash
# 本地镜像 GitHub Actions（.github/workflows/ci.yml），用于无远端时验证同一组检查。
#
#   bash scripts/ci.sh                 # 全量：后端 + 前端 + E2E
#   CI_SKIP_E2E=1 bash scripts/ci.sh   # 跳过浏览器端（快速回归）
#   CI_SKIP_COVERAGE=1 bash scripts/ci.sh  # 跳过后端覆盖率门槛
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 与 .github/workflows/ci.yml 的 --cov-fail-under 保持一致
COVERAGE_MIN="${COVERAGE_MIN:-83}"

step() { printf '\n==> %s\n' "$1"; }

step "Runtime"
python --version
node --version
npm --version

step "Backend tests"
if [[ "${CI_SKIP_COVERAGE:-0}" == "1" ]]; then
  (cd backend && python -m pytest)
else
  (cd backend && python -m pytest \
    --cov=medsta \
    --cov-report=term-missing \
    --cov-fail-under="${COVERAGE_MIN}")
fi

step "Frontend lint"
(cd frontend && npm run lint)

step "Frontend build"
(cd frontend && npm run build)

step "Frontend unit and interaction tests"
(cd frontend && npm test)

if [[ "${CI_SKIP_E2E:-0}" == "1" ]]; then
  step "E2E skipped (CI_SKIP_E2E=1)"
else
  step "Browser end-to-end tests"
  (cd frontend && npm run test:e2e)
fi

step "All checks passed"

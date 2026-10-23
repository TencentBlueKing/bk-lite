#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${SERVER_DIR}"

DB_ENGINE="${DB_ENGINE:-sqlite}" \
DB_NAME="${DB_NAME:-:memory:}" \
SECRET_KEY="${SECRET_KEY:-workflow-test-only}" \
ENABLE_CELERY="${ENABLE_CELERY:-true}" \
uv run pytest apps/workflow/tests \
  -o addopts='' \
  --import-mode=importlib \
  --create-db \
  --cov=apps.workflow \
  --cov-config=.coveragerc.workflow \
  --cov-report=term-missing:skip-covered \
  --cov-fail-under=75 \
  "$@"

#!/usr/bin/env bash
# 启动作业 Celery worker。只消费 job 队列。
# 和 API、Beat 使用同一套数据库与 Broker。本环境只运行一个 Beat。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SERVER_DIR="${ROOT_DIR}/server"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv 未安装。请先在本机安装并加入 PATH。"
  exit 1
fi

cd "${SERVER_DIR}"
uv run celery -A apps.core.celery worker \
  --loglevel=info \
  --pool prefork \
  --concurrency="${JOB_CELERY_CONCURRENCY:-2}" \
  --max-tasks-per-child="${CELERY_MAX_TASKS_PER_CHILD:-200}" \
  --max-memory-per-child="${CELERY_MAX_MEMORY_PER_CHILD:-512000}" \
  -Q job \
  -n "job@%h"

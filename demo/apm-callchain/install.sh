#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -U pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/opentelemetry-bootstrap" -a install >/dev/null || true
echo "依赖已安装。"

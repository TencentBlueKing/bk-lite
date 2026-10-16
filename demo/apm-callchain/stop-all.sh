#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT/run"
for name in inventory payment catalog order gateway loop; do
  pid_file="$ROOT/run/${name}.pid"
  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
done
echo "五个服务已停止。"

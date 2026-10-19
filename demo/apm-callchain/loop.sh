#!/bin/bash
# 持续打流量，让服务详情 15m/1h 窗口里一直有新数据。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT/run"
if [[ "${BACKGROUND:-0}" == "1" ]]; then
  BACKGROUND=0 nohup "$ROOT/loop.sh" >>"$ROOT/run/loop.log" 2>&1 &
  echo $! >"$ROOT/run/loop.pid"
  echo "loop pid $(cat "$ROOT/run/loop.pid")  日志 run/loop.log"
  exit 0
fi
while true; do
  "$ROOT/send.sh" || true
  sleep 8
done

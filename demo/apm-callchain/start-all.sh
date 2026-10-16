#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
"$ROOT/stop-all.sh"
for name in inventory payment catalog order gateway; do
  BACKGROUND=1 "$ROOT/run.sh" "$name"
done
echo "五个服务已在后台启动。"

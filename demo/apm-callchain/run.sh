#!/bin/bash
# 单独启动一个服务，并注入探针。
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
source "$ROOT/env.sh"
NAME=${1:?用法: ./run.sh gateway|order|catalog|inventory|payment}
case "$NAME" in
  gateway) SCRIPT="$ROOT/services/gateway.py" ;;
  order) SCRIPT="$ROOT/services/order.py" ;;
  catalog) SCRIPT="$ROOT/services/catalog.py" ;;
  inventory) SCRIPT="$ROOT/services/inventory.py" ;;
  payment) SCRIPT="$ROOT/services/payment.py" ;;
  *) echo "未知服务: $NAME" >&2; exit 1 ;;
esac
if [[ ! -x "$ROOT/.venv/bin/opentelemetry-instrument" ]]; then
  echo "还没有虚拟环境，先执行 ./install.sh" >&2
  exit 1
fi
export OTEL_SERVICE_INSTANCE_ID="${NAME}-$(hostname -s)"
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=${OTEL_SERVICE_NAMESPACE},service.name=${NAME},service.version=1.0.0,deployment.environment=${OTEL_DEPLOYMENT_ENV},service.instance.id=${OTEL_SERVICE_INSTANCE_ID}"
export PYTHONPATH="$ROOT/services${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
if [[ "${BACKGROUND:-0}" == "1" ]]; then
  mkdir -p "$ROOT/run"
  nohup "$ROOT/.venv/bin/opentelemetry-instrument" "$ROOT/.venv/bin/python" "$SCRIPT" >>"$ROOT/run/${NAME}.log" 2>&1 &
  echo $! >"$ROOT/run/${NAME}.pid"
  echo "$NAME pid $(cat "$ROOT/run/${NAME}.pid")  日志 run/${NAME}.log"
else
  exec "$ROOT/.venv/bin/opentelemetry-instrument" "$ROOT/.venv/bin/python" "$SCRIPT"
fi

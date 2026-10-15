# 上报地址和命名空间写在 env.local。namespace 必须是 APM 里已经存在的应用，
# 否则目录对账会丢掉这些服务。
_ENV_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ -f "${_ENV_DIR}/env.local" ]]; then
  # shellcheck disable=SC1091
  source "${_ENV_DIR}/env.local"
fi
if [[ -z "${APM_OTLP_ENDPOINT:-}" || -z "${OTEL_SERVICE_NAMESPACE:-}" ]]; then
  echo "先复制 env.local.example 为 env.local，填好 APM_OTLP_ENDPOINT 和 OTEL_SERVICE_NAMESPACE" >&2
  exit 1
fi
export OTEL_EXPORTER_OTLP_ENDPOINT="${APM_OTLP_ENDPOINT}"
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TIMEOUT=10000
unset OTEL_EXPORTER_OTLP_TRACES_ENDPOINT
export OTEL_PROPAGATORS=tracecontext,baggage
export OTEL_TRACES_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_SERVICE_NAMESPACE="${OTEL_SERVICE_NAMESPACE}"
export OTEL_DEPLOYMENT_ENV="${OTEL_DEPLOYMENT_ENV:-production}"
export PYTHONUNBUFFERED=1
# 本机失效的 HTTP 代理会把 OTLP 打到 127.0.0.1，Span 发不出去。
export NO_PROXY="${NO_PROXY:-*}"
export no_proxy="${NO_PROXY}"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export PGHOST="${PGHOST:-}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-}"
export PGPASSWORD="${PGPASSWORD:-}"
export PGDATABASE="${PGDATABASE:-}"
export REDIS_URL="${REDIS_URL:-}"

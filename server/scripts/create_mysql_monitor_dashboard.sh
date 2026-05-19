#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/templates"
VENV_PYTHON_DEFAULT="${SERVER_DIR}/.venv/bin/python"
CREATE_MONITOR_INSTANCE_ENTRY="${SERVER_DIR}/apps/monitor/management/commands/create_monitor_instance.py"

: "${MYSQL_MONITOR_OBJECT_ID:?required}"
: "${MYSQL_MONITOR_PLUGIN_ID:?required}"
MYSQL_GROUP_ID="${MYSQL_GROUP_ID:-1}"
: "${MYSQL_NODE_ID:?required}"

: "${MYSQL_HOST:?required}"
: "${MYSQL_PORT:?required}"
: "${MYSQL_USERNAME:?required}"
: "${MYSQL_PASSWORD:?required}"

: "${OA_TARGET_DIRECTORY_ID:?required}"

MYSQL_INSTANCE_ID="${MYSQL_INSTANCE_ID:-}"
MYSQL_INSTANCE_NAME="${MYSQL_INSTANCE_NAME:-${MYSQL_HOST}:${MYSQL_PORT}}"
MYSQL_INSTANCE_TYPE="${MYSQL_INSTANCE_TYPE:-mysql}"
MYSQL_INTERVAL_SECONDS="${MYSQL_INTERVAL_SECONDS:-10}"
MYSQL_INSTANCE_ID_LINE=""

OA_CREATED_BY="${OA_CREATED_BY:-admin}"

OA_DASHBOARD_NAME="${OA_DASHBOARD_NAME:-MySQL-${MYSQL_INSTANCE_NAME}-趋势}"
OA_DASHBOARD_DESC="${OA_DASHBOARD_DESC:-MySQL 自动导入趋势图}"
OA_EXISTING_DATASOURCE_NAME="${OA_EXISTING_DATASOURCE_NAME:-查询时间范围内的指标数据}"
OA_EXISTING_DATASOURCE_REST_API="${OA_EXISTING_DATASOURCE_REST_API:-monitor/mm_query_range}"
OA_DATASOURCE_KEY="${OA_DATASOURCE_KEY:-${OA_EXISTING_DATASOURCE_NAME}::${OA_EXISTING_DATASOURCE_REST_API}}"

OA_WIDGET_ID="${OA_WIDGET_ID:-mysql-monitor-widget}"
OA_WIDGET_TITLE="${OA_WIDGET_TITLE:-MySQL 指标趋势}"
OA_WIDGET_DESC="${OA_WIDGET_DESC:-}"
OA_WIDGET_X="${OA_WIDGET_X:-0}"
OA_WIDGET_Y="${OA_WIDGET_Y:-0}"
OA_WIDGET_W="${OA_WIDGET_W:-6}"
OA_WIDGET_H="${OA_WIDGET_H:-4}"
OA_CHART_TYPE="${OA_CHART_TYPE:-line}"

OA_QUERY_METRIC="${OA_QUERY_METRIC:-mysql_threads_connected}"
OA_QUERY_EXPR="${OA_QUERY_EXPR:-}"
OA_QUERY_STEP="${OA_QUERY_STEP:-5m}"
OA_QUERY_TIME_RANGE="${OA_QUERY_TIME_RANGE:-10080}"

METRIC_READY_LOOKBACK_SECONDS="${METRIC_READY_LOOKBACK_SECONDS:-600}"
METRIC_READY_RETRIES="${METRIC_READY_RETRIES:-30}"
METRIC_READY_INTERVAL_SECONDS="${METRIC_READY_INTERVAL_SECONDS:-10}"

KEEP_WORKDIR="${KEEP_WORKDIR:-1}"
WORKDIR="${WORKDIR:-$(mktemp -d "/tmp/bklite-mysql-dashboard.XXXXXX")}" 

MONITOR_REQUEST_YAML="${WORKDIR}/monitor-request.yaml"
MONITOR_RESULT_YAML="${WORKDIR}/monitor-result.yaml"
OA_IMPORT_YAML="${WORKDIR}/oa-import.yaml"
INSTANCE_LABEL_FILE="${WORKDIR}/instance-label.txt"

DJANGO_PYTHON="${DJANGO_PYTHON:-${VENV_PYTHON_DEFAULT}}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

warn() {
  printf '[%s] WARN: %s\n' "$(date '+%F %T')" "$*" >&2
}

fail() {
  printf '[%s] ERROR: %s\n' "$(date '+%F %T')" "$*" >&2
  printf '[%s] workdir: %s\n' "$(date '+%F %T')" "${WORKDIR}" >&2
  exit 1
}

cleanup() {
  if [[ "${KEEP_WORKDIR}" == "1" ]]; then
    log "workdir kept at: ${WORKDIR}"
  else
    rm -rf "${WORKDIR}"
  fi
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing command: $1"
}

assert_int() {
  [[ "$1" =~ ^[0-9]+$ ]] || fail "$2 must be integer, got: $1"
}

assert_nonempty() {
  [[ -n "$1" ]] || fail "$2 must not be empty"
}

render_template() {
  local template_path="$1"
  local output_path="$2"
  TEMPLATE_PATH="${template_path}" OUTPUT_PATH="${output_path}" python3 <<'PY'
import os
import re
from pathlib import Path

template = Path(os.environ["TEMPLATE_PATH"]).read_text(encoding="utf-8")

pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def replace(match):
    key = match.group(1)
    if key not in os.environ:
        raise SystemExit(f"missing template variable: {key}")
    return os.environ[key]

rendered = pattern.sub(replace, template)
Path(os.environ["OUTPUT_PATH"]).write_text(rendered, encoding="utf-8")
PY
}

check_tools() {
  require_cmd python3
  [[ -x "${DJANGO_PYTHON}" ]] || fail "django python not found or not executable: ${DJANGO_PYTHON}"
}

check_inputs() {
  [[ -f "${SERVER_DIR}/manage.py" ]] || fail "manage.py not found: ${SERVER_DIR}/manage.py"
  [[ -f "${CREATE_MONITOR_INSTANCE_ENTRY}" ]] || fail "create_monitor_instance entrypoint not found: ${CREATE_MONITOR_INSTANCE_ENTRY}"
  [[ -f "${TEMPLATE_DIR}/mysql_monitor_instance.request.yaml.tpl" ]] || fail "monitor template missing"
  [[ -f "${TEMPLATE_DIR}/mysql_operation_analysis_dashboard.yaml.tpl" ]] || fail "dashboard template missing"

  assert_int "${MYSQL_MONITOR_OBJECT_ID}" "MYSQL_MONITOR_OBJECT_ID"
  assert_int "${MYSQL_MONITOR_PLUGIN_ID}" "MYSQL_MONITOR_PLUGIN_ID"
  assert_int "${MYSQL_GROUP_ID}" "MYSQL_GROUP_ID"
  assert_int "${MYSQL_PORT}" "MYSQL_PORT"
  assert_int "${MYSQL_INTERVAL_SECONDS}" "MYSQL_INTERVAL_SECONDS"
  assert_int "${OA_TARGET_DIRECTORY_ID}" "OA_TARGET_DIRECTORY_ID"
  assert_int "${OA_QUERY_TIME_RANGE}" "OA_QUERY_TIME_RANGE"
  assert_int "${METRIC_READY_LOOKBACK_SECONDS}" "METRIC_READY_LOOKBACK_SECONDS"
  assert_int "${METRIC_READY_RETRIES}" "METRIC_READY_RETRIES"
  assert_int "${METRIC_READY_INTERVAL_SECONDS}" "METRIC_READY_INTERVAL_SECONDS"
  assert_int "${OA_WIDGET_X}" "OA_WIDGET_X"
  assert_int "${OA_WIDGET_Y}" "OA_WIDGET_Y"
  assert_int "${OA_WIDGET_W}" "OA_WIDGET_W"
  assert_int "${OA_WIDGET_H}" "OA_WIDGET_H"

  assert_nonempty "${MYSQL_NODE_ID}" "MYSQL_NODE_ID"
  assert_nonempty "${MYSQL_HOST}" "MYSQL_HOST"
  assert_nonempty "${MYSQL_USERNAME}" "MYSQL_USERNAME"
  assert_nonempty "${MYSQL_PASSWORD}" "MYSQL_PASSWORD"
  assert_nonempty "${MYSQL_INSTANCE_NAME}" "MYSQL_INSTANCE_NAME"
  assert_nonempty "${OA_DATASOURCE_KEY}" "OA_DATASOURCE_KEY"
  assert_nonempty "${OA_EXISTING_DATASOURCE_NAME}" "OA_EXISTING_DATASOURCE_NAME"
  assert_nonempty "${OA_EXISTING_DATASOURCE_REST_API}" "OA_EXISTING_DATASOURCE_REST_API"
  assert_nonempty "${OA_DASHBOARD_NAME}" "OA_DASHBOARD_NAME"
  assert_nonempty "${OA_WIDGET_ID}" "OA_WIDGET_ID"
  assert_nonempty "${OA_CHART_TYPE}" "OA_CHART_TYPE"
}

preflight_local_django() {
  log "running local django preflight"
  (
    cd "${SERVER_DIR}"
    MYSQL_MONITOR_OBJECT_ID="${MYSQL_MONITOR_OBJECT_ID}" \
    MYSQL_MONITOR_PLUGIN_ID="${MYSQL_MONITOR_PLUGIN_ID}" \
    OA_TARGET_DIRECTORY_ID="${OA_TARGET_DIRECTORY_ID}" \
    MYSQL_GROUP_ID="${MYSQL_GROUP_ID}" \
    OA_EXISTING_DATASOURCE_NAME="${OA_EXISTING_DATASOURCE_NAME}" \
    OA_EXISTING_DATASOURCE_REST_API="${OA_EXISTING_DATASOURCE_REST_API}" \
    "${DJANGO_PYTHON}" manage.py shell <<'PY'
import os
import sys
from django.apps import apps

MonitorObject = apps.get_model("monitor", "MonitorObject")
MonitorPlugin = apps.get_model("monitor", "MonitorPlugin")
Directory = apps.get_model("operation_analysis", "Directory")
DataSourceAPIModel = apps.get_model("operation_analysis", "DataSourceAPIModel")

errors = []
if not MonitorObject.objects.filter(id=int(os.environ["MYSQL_MONITOR_OBJECT_ID"])).exists():
    errors.append(f"monitor object not found: {os.environ['MYSQL_MONITOR_OBJECT_ID']}")
if not MonitorPlugin.objects.filter(id=int(os.environ["MYSQL_MONITOR_PLUGIN_ID"])).exists():
    errors.append(f"monitor plugin not found: {os.environ['MYSQL_MONITOR_PLUGIN_ID']}")
directory = Directory.objects.filter(id=int(os.environ["OA_TARGET_DIRECTORY_ID"])).first()
if not directory:
    errors.append(f"target directory not found: {os.environ['OA_TARGET_DIRECTORY_ID']}")
else:
    groups = directory.groups or []
    if int(os.environ["MYSQL_GROUP_ID"]) not in groups:
        errors.append(
            f"target directory {os.environ['OA_TARGET_DIRECTORY_ID']} groups {groups} do not include MYSQL_GROUP_ID={os.environ['MYSQL_GROUP_ID']}"
        )
if not DataSourceAPIModel.objects.filter(
    name=os.environ["OA_EXISTING_DATASOURCE_NAME"],
    rest_api=os.environ["OA_EXISTING_DATASOURCE_REST_API"],
).exists():
    errors.append(
        "operation_analysis datasource not found: "
        f"name={os.environ['OA_EXISTING_DATASOURCE_NAME']}, "
        f"rest_api={os.environ['OA_EXISTING_DATASOURCE_REST_API']}"
    )

if errors:
    for item in errors:
        print(item)
    sys.exit(1)

print("preflight ok")
PY
  ) || fail "local django preflight failed"
}

render_monitor_yaml() {
  log "rendering monitor yaml"
  if [[ -n "${MYSQL_INSTANCE_ID}" ]]; then
    MYSQL_INSTANCE_ID_LINE="    instance_id: \"${MYSQL_INSTANCE_ID}\""
  else
    MYSQL_INSTANCE_ID_LINE=""
  fi
  export MYSQL_INSTANCE_ID_LINE
  render_template "${TEMPLATE_DIR}/mysql_monitor_instance.request.yaml.tpl" "${MONITOR_REQUEST_YAML}"
}

create_monitor_instance() {
  log "creating mysql monitor instance via create_monitor_instance.py entrypoint"
  (
    cd "${SERVER_DIR}"
    "${DJANGO_PYTHON}" manage.py create_monitor_instance \
      --config "${MONITOR_REQUEST_YAML}" \
      --output "${MONITOR_RESULT_YAML}"
  ) || fail "create_monitor_instance failed"
}

parse_monitor_result() {
  log "validating monitor result"
  (
    cd "${SERVER_DIR}"
    RESULT_YAML="${MONITOR_RESULT_YAML}" \
    INSTANCE_LABEL_FILE="${INSTANCE_LABEL_FILE}" \
    "${DJANGO_PYTHON}" manage.py shell <<'PY'
import os
import sys
import yaml

path = os.environ["RESULT_YAML"]
label_out = os.environ["INSTANCE_LABEL_FILE"]
with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

instances = (((data.get("result") or {}).get("instances")) or [])
if not instances:
    print("no created instances found in result.yaml")
    sys.exit(1)

instance = instances[0]
configs = instance.get("configs") or []
if not configs:
    print("instance created but no collect configs generated")
    sys.exit(1)

label_values = instance.get("instance_id_values") or []
if not label_values:
    print("missing instance_id_values in result.yaml")
    sys.exit(1)

with open(label_out, "w", encoding="utf-8") as f:
    f.write(str(label_values[0]).strip())

print(f"instance_label={label_values[0]}")
PY
  ) || fail "monitor result validation failed"

INSTANCE_LABEL="$(cat "${INSTANCE_LABEL_FILE}")"
  assert_nonempty "${INSTANCE_LABEL}" "INSTANCE_LABEL"

  if [[ -z "${OA_QUERY_EXPR}" ]]; then
    OA_QUERY_EXPR="${OA_QUERY_METRIC}{instance_id=\"${INSTANCE_LABEL}\"}"
  fi

  export OA_QUERY_EXPR
  log "resolved instance label: ${INSTANCE_LABEL}"
  log "effective query expr: ${OA_QUERY_EXPR}"
}

probe_metric_once() {
  (
    cd "${SERVER_DIR}"
    OA_QUERY_EXPR="${OA_QUERY_EXPR}" \
    OA_QUERY_STEP="${OA_QUERY_STEP}" \
    METRIC_READY_LOOKBACK_SECONDS="${METRIC_READY_LOOKBACK_SECONDS}" \
    "${DJANGO_PYTHON}" manage.py shell <<'PY'
import os
import sys
import time
from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

query = os.environ["OA_QUERY_EXPR"]
step = os.environ["OA_QUERY_STEP"]
lookback = int(os.environ["METRIC_READY_LOOKBACK_SECONDS"])

end_ts = int(time.time())
start_ts = end_ts - lookback

resp = VictoriaMetricsAPI().query_range(query, start_ts, end_ts, step)
result = (((resp or {}).get("data") or {}).get("result")) or []
has_values = any(item.get("values") for item in result)
print("ready" if has_values else "not_ready")
sys.exit(0 if has_values else 1)
PY
  )
}

wait_metric_ready() {
  log "waiting mysql metric ready"
  local attempt=1
  while (( attempt <= METRIC_READY_RETRIES )); do
    if probe_metric_once >/dev/null 2>&1; then
      log "metric ready on attempt ${attempt}/${METRIC_READY_RETRIES}"
      return 0
    fi
    log "metric not ready yet, retry ${attempt}/${METRIC_READY_RETRIES}"
    sleep "${METRIC_READY_INTERVAL_SECONDS}"
    attempt=$((attempt + 1))
  done
  fail "metric readiness timeout for query: ${OA_QUERY_EXPR}"
}

render_dashboard_yaml() {
  log "rendering operation analysis import yaml"
  render_template "${TEMPLATE_DIR}/mysql_operation_analysis_dashboard.yaml.tpl" "${OA_IMPORT_YAML}"
}

apply_oa_dashboard_via_django() {
  log "applying operation analysis datasource and dashboard via django orm"
  (
    cd "${SERVER_DIR}"
    OA_IMPORT_YAML="${OA_IMPORT_YAML}" \
    OA_TARGET_DIRECTORY_ID="${OA_TARGET_DIRECTORY_ID}" \
    MYSQL_GROUP_ID="${MYSQL_GROUP_ID}" \
    OA_CREATED_BY="${OA_CREATED_BY}" \
    OA_DATASOURCE_KEY="${OA_DATASOURCE_KEY}" \
    OA_EXISTING_DATASOURCE_NAME="${OA_EXISTING_DATASOURCE_NAME}" \
    OA_EXISTING_DATASOURCE_REST_API="${OA_EXISTING_DATASOURCE_REST_API}" \
    "${DJANGO_PYTHON}" manage.py shell <<'PY'
import json
import os
import sys
import yaml

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory

yaml_path = os.environ["OA_IMPORT_YAML"]
target_directory_id = int(os.environ["OA_TARGET_DIRECTORY_ID"])
group_id = int(os.environ["MYSQL_GROUP_ID"])
datasource_name = os.environ["OA_EXISTING_DATASOURCE_NAME"]
datasource_rest_api = os.environ["OA_EXISTING_DATASOURCE_REST_API"]

with open(yaml_path, "r", encoding="utf-8") as f:
    doc = yaml.safe_load(f) or {}

directory = Directory.objects.filter(id=target_directory_id).first()
if not directory:
    print(f"target directory not found: {target_directory_id}")
    sys.exit(1)

ds_obj = DataSourceAPIModel.objects.filter(name=datasource_name, rest_api=datasource_rest_api).first()
if not ds_obj:
    print(f"datasource not found: name={datasource_name}, rest_api={datasource_rest_api}")
    sys.exit(1)

dashboards = doc.get("dashboards") or []
if not dashboards:
    print("no dashboard section found in rendered yaml")
    sys.exit(1)

dashboard_item = dashboards[0]

view_sets = dashboard_item.get("view_sets") or []
for widget in view_sets:
    value_config = widget.get("valueConfig") or {}
    if value_config.get("dataSource") == os.environ["OA_DATASOURCE_KEY"]:
        value_config["dataSource"] = ds_obj.id
        widget["valueConfig"] = value_config

dash_defaults = {
    "desc": dashboard_item.get("desc", ""),
    "directory": directory,
    "filters": dashboard_item.get("filters", {}),
    "other": dashboard_item.get("other", {}),
    "view_sets": view_sets,
    "groups": [group_id],
    "updated_by": os.environ["OA_CREATED_BY"],
}

dashboard = Dashboard.objects.filter(name=dashboard_item["name"]).first()
dash_action = "updated" if dashboard else "created"
if dashboard:
    for key, value in dash_defaults.items():
        setattr(dashboard, key, value)
    dashboard.save()
else:
    dashboard = Dashboard.objects.create(
        name=dashboard_item["name"],
        created_by=os.environ["OA_CREATED_BY"],
        **dash_defaults,
    )

print(json.dumps({
    "datasource": {"id": ds_obj.id, "action": "reused", "name": ds_obj.name},
    "dashboard": {"id": dashboard.id, "action": dash_action, "name": dashboard.name},
}, ensure_ascii=False))
PY
  ) || fail "failed to apply operation analysis datasource/dashboard via django"
}

print_summary() {
  log "completed successfully"
  log "dashboard name: ${OA_DASHBOARD_NAME}"
  log "datasource name: ${OA_EXISTING_DATASOURCE_NAME}"
  log "instance label: ${INSTANCE_LABEL}"
  log "query expr: ${OA_QUERY_EXPR}"
}

main() {
  check_tools
  check_inputs
  preflight_local_django

  export MYSQL_MONITOR_OBJECT_ID MYSQL_MONITOR_PLUGIN_ID MYSQL_GROUP_ID MYSQL_NODE_ID
  export MYSQL_HOST MYSQL_PORT MYSQL_USERNAME MYSQL_PASSWORD MYSQL_INSTANCE_ID MYSQL_INSTANCE_NAME MYSQL_INSTANCE_TYPE MYSQL_INTERVAL_SECONDS MYSQL_INSTANCE_ID_LINE
  export OA_CREATED_BY OA_EXISTING_DATASOURCE_NAME OA_EXISTING_DATASOURCE_REST_API OA_DATASOURCE_KEY
  export OA_DASHBOARD_NAME OA_DASHBOARD_DESC
  export OA_WIDGET_ID OA_WIDGET_TITLE OA_WIDGET_DESC OA_WIDGET_X OA_WIDGET_Y OA_WIDGET_W OA_WIDGET_H OA_CHART_TYPE OA_QUERY_STEP OA_QUERY_TIME_RANGE

  render_monitor_yaml
  create_monitor_instance
  parse_monitor_result
  wait_metric_ready
  render_dashboard_yaml
  apply_oa_dashboard_via_django
  print_summary
}

main "$@"

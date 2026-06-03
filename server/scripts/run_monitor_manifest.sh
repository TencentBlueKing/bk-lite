#!/usr/bin/env bash
set -euo pipefail

MANIFEST_PATH="${1:?usage: run_monitor_manifest.sh <manifest.yaml>}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DJANGO_PYTHON="${DJANGO_PYTHON:-${SERVER_DIR}/.venv/bin/python}"

WORKDIR="${WORKDIR:-$(mktemp -d "/tmp/bklite-monitor-manifest.XXXXXX")}" 
OUTPUT_DIR="${OUTPUT_DIR:-${WORKDIR}/outputs}"
SUMMARY_FILE="${OUTPUT_DIR}/summary.yaml"
OA_GROUP_DIR="${OUTPUT_DIR}/oa-groups"
KEEP_WORKDIR="${KEEP_WORKDIR:-1}"
TEMPLATE_DIR="${SCRIPT_DIR}/templates"
METRIC_READY_LOOKBACK_SECONDS="${METRIC_READY_LOOKBACK_SECONDS:-600}"
METRIC_READY_RETRIES="${METRIC_READY_RETRIES:-30}"
METRIC_READY_INTERVAL_SECONDS="${METRIC_READY_INTERVAL_SECONDS:-20}"
MYSQL_GROUP_ID="${MYSQL_GROUP_ID:-1}"
export MYSQL_GROUP_ID
DEFAULT_NODEMGMT_WORK_NODE="${DEFAULT_NODEMGMT_WORK_NODE:-}"
INSTALL_AGENT_TIMEOUT_SECONDS="${INSTALL_AGENT_TIMEOUT_SECONDS:-900}"
INSTALL_AGENT_POLL_INTERVAL_SECONDS="${INSTALL_AGENT_POLL_INTERVAL_SECONDS:-10}"

mkdir -p "${OUTPUT_DIR}"
mkdir -p "${OA_GROUP_DIR}"

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
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

require_file() {
  [[ -f "$1" ]] || fail "file not found: $1"
}

check_env() {
  require_file "${MANIFEST_PATH}"
  require_file "${SERVER_DIR}/manage.py"
  [[ -x "${DJANGO_PYTHON}" ]] || fail "django python not executable: ${DJANGO_PYTHON}"
  require_file "${TEMPLATE_DIR}/mysql_operation_analysis_dashboard.yaml.tpl"
}

validate_manifest() {
  MANIFEST_PATH="${MANIFEST_PATH}" "${DJANGO_PYTHON}" <<'PY'
import os
import sys
import yaml

path = os.environ["MANIFEST_PATH"]
with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

errors = []

if data.get("version") != 1:
    errors.append("manifest version must be 1")

registrations = data.get("registrations")
if not isinstance(registrations, list) or not registrations:
    errors.append("registrations must be a non-empty list")

keys = []
defaults = data.get("defaults", {}) or {}
default_node_ids = defaults.get("node_ids") or []
default_node_name = defaults.get("node_name")
default_node_ip = defaults.get("node_ip")
oa_defaults = defaults.get("oa", {}) or {}
shared_dashboard_configs = {}

for i, item in enumerate(registrations or []):
    if not isinstance(item, dict):
        errors.append(f"registrations[{i}] must be an object")
        continue
    for field in ["key", "collector", "collect_type", "configs", "instances"]:
        if field not in item or item[field] in [None, ""]:
            errors.append(f"registrations[{i}].{field} is required")
    if item.get("monitor_object_id") in [None, ""] and not item.get("monitor_object_name"):
        errors.append(
            f"registrations[{i}].monitor_object_id is required unless monitor_object_name is provided"
        )
    if item.get("monitor_plugin_id") in [None, ""] and not item.get("plugin_name"):
        errors.append(
            f"registrations[{i}].monitor_plugin_id is required unless plugin_name is provided"
        )
    if "key" in item:
        keys.append(item["key"])
    if not isinstance(item.get("configs"), list) or not item.get("configs"):
        errors.append(f"registrations[{i}].configs must be a non-empty list")
    if not isinstance(item.get("instances"), list) or not item.get("instances"):
        errors.append(f"registrations[{i}].instances must be a non-empty list")
    oa = item.get("operation_analysis") or {}
    alarm_policies = item.get("alarm_policies") or []
    if oa.get("enabled"):
        if len(item.get("instances") or []) != 1:
            errors.append(f"registrations[{i}].operation_analysis currently requires exactly one instance")
        if not oa.get("target_directory_id"):
            errors.append(f"registrations[{i}].operation_analysis.target_directory_id is required when enabled")
        dashboard_key = oa.get("dashboard_key")
        if not dashboard_key and item.get("collect_type") != "database":
            errors.append(f"registrations[{i}].operation_analysis currently supports only database registrations unless dashboard_key is provided")
        if dashboard_key and item.get("collect_type") != "database" and not (oa.get("query_expr") or oa.get("query_metric")):
            errors.append(f"registrations[{i}].operation_analysis for non-database registrations requires query_expr or query_metric when dashboard_key is provided")
        effective_oa = oa_defaults | oa
        effective_dashboard_key = dashboard_key or item.get("key")
        dashboard_config = {
            "target_directory_id": effective_oa.get("target_directory_id", ""),
            "dashboard_name": effective_oa.get("dashboard_name", f"{item.get('key')}-dashboard"),
            "dashboard_desc": effective_oa.get("dashboard_desc", "Auto-created from monitor manifest"),
            "datasource_name": effective_oa.get("datasource_name", "查询时间范围内的指标数据"),
            "datasource_rest_api": effective_oa.get("datasource_rest_api", "monitor/mm_query_range"),
            "created_by": effective_oa.get("created_by", "admin"),
        }
        existing = shared_dashboard_configs.get(effective_dashboard_key)
        if existing and existing != dashboard_config:
            errors.append(
                f"registrations[{i}].operation_analysis.dashboard_key={effective_dashboard_key!r} must use the same dashboard-level configuration as other registrations in the group"
            )
        else:
            shared_dashboard_configs[effective_dashboard_key] = dashboard_config
    if alarm_policies:
        if not isinstance(alarm_policies, list):
            errors.append(f"registrations[{i}].alarm_policies must be a list")
        policy_keys = set()
        for k, policy in enumerate(alarm_policies or []):
            if not isinstance(policy, dict):
                errors.append(f"registrations[{i}].alarm_policies[{k}] must be an object")
                continue
            for field in [
                "policy_key",
                "name",
                "alert_name",
                "collect_type",
                "query_condition",
                "source",
                "schedule",
                "period",
                "algorithm",
                "threshold",
                "enable",
                "enable_alerts",
            ]:
                if field not in policy:
                    errors.append(f"registrations[{i}].alarm_policies[{k}].{field} is required")
            if "policy_key" in policy:
                if policy["policy_key"] in policy_keys:
                    errors.append(f"registrations[{i}].alarm_policies policy_key must be unique")
                policy_keys.add(policy["policy_key"])
            source = policy.get("source") or {}
            if source != {"from_registration_instances": True}:
                errors.append(
                    f"registrations[{i}].alarm_policies[{k}].source currently only supports {{from_registration_instances: true}}"
                )
    for j, instance in enumerate(item.get("instances") or []):
        if not isinstance(instance, dict):
            errors.append(f"registrations[{i}].instances[{j}] must be an object")
            continue
        if not instance.get("instance_name"):
            errors.append(f"registrations[{i}].instances[{j}].instance_name is required")
        has_node_locator = bool(instance.get("node_ids") or instance.get("node_name") or instance.get("node_ip"))
        install_agent = instance.get("install_agent") or {}
        if install_agent.get("enabled"):
            auth_type = install_agent.get("auth_type")
            if auth_type not in ["password", "private_key"]:
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.auth_type must be password or private_key"
                )
            if not install_agent.get("username"):
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.username is required when install_agent is enabled"
                )
            if auth_type == "password" and not install_agent.get("password"):
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.password is required when auth_type=password"
                )
            if auth_type == "private_key" and not install_agent.get("private_key"):
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.private_key is required when auth_type=private_key"
                )
            if not install_agent.get("cpu_architecture"):
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.cpu_architecture is required when install_agent is enabled"
                )
            install_os = install_agent.get("os")
            if install_os not in [None, "", "linux"]:
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent.os currently only supports linux"
                )
            install_host = instance.get("node_ip") or default_node_ip or instance.get("host")
            if not install_host:
                errors.append(
                    f"registrations[{i}].instances[{j}].install_agent requires host or node_ip (or defaults.node_ip)"
                )
        has_default_node_locator = bool(default_node_ids or default_node_name or default_node_ip)
        if not has_node_locator and not has_default_node_locator and not install_agent.get("enabled"):
            errors.append(
                f"registrations[{i}].instances[{j}] must provide node_ids, node_name, or node_ip unless defaults provide one or install_agent is enabled"
            )

if len(keys) != len(set(keys)):
    errors.append("registration keys must be unique")

if errors:
    for e in errors:
        print(e)
    sys.exit(1)

print("manifest ok")
PY
}

list_registration_keys() {
  MANIFEST_PATH="${MANIFEST_PATH}" "${DJANGO_PYTHON}" <<'PY'
import os
import ast
import yaml

with open(os.environ["MANIFEST_PATH"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

for item in data.get("registrations", []):
    print(item["key"])
PY
}

render_request_yaml() {
  local prepared_reg_file="$1"
  local out="$2"

  PREPARED_REG_FILE="${prepared_reg_file}" OUT_PATH="${out}" PYTHONPATH="${SERVER_DIR}:${SERVER_DIR}/..:${PYTHONPATH:-}" "${DJANGO_PYTHON}" <<'PY'
import os
from copy import deepcopy
import yaml

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django

django.setup()

from apps.monitor.models import MonitorObject, MonitorPlugin
from apps.node_mgmt.models import Node

path = os.environ["PREPARED_REG_FILE"]
out_path = os.environ["OUT_PATH"]

with open(path, "r", encoding="utf-8") as f:
    payload = yaml.safe_load(f) or {}

defaults = payload.get("defaults", {}) or {}
reg = payload.get("registration") or {}
reg_key = reg.get("key", "unknown-registration")

def fail(message):
    raise SystemExit(f"{reg_key}: {message}")


def resolve_monitor_object():
    monitor_object_id = reg.get("monitor_object_id")
    monitor_object_name = reg.get("monitor_object_name")

    if monitor_object_id not in [None, ""]:
        obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not obj:
            fail(f"monitor_object_id not found: {monitor_object_id}")
        return obj

    if not monitor_object_name:
        fail("monitor_object_name is required when monitor_object_id is omitted")

    objects = MonitorObject.objects.filter(name=monitor_object_name)
    count = objects.count()
    if count == 0:
        fail(f"monitor object not found: {monitor_object_name}")
    if count > 1:
        fail(f"monitor object lookup ambiguous: {monitor_object_name}")
    return objects.first()


def resolve_monitor_plugin():
    monitor_plugin_id = reg.get("monitor_plugin_id")
    plugin_name = reg.get("plugin_name")

    if monitor_plugin_id not in [None, ""]:
        plugin = MonitorPlugin.objects.filter(id=monitor_plugin_id).first()
        if not plugin:
            fail(f"monitor_plugin_id not found: {monitor_plugin_id}")
        return plugin

    if not plugin_name:
        fail("plugin_name is required when monitor_plugin_id is omitted")

    plugins = MonitorPlugin.objects.filter(
        collector=reg["collector"],
        collect_type=reg["collect_type"],
        name=plugin_name,
    )
    count = plugins.count()
    if count == 0:
        fail(
            "plugin not found for "
            f"collector={reg['collector']}, collect_type={reg['collect_type']}, plugin_name={plugin_name}"
        )
    if count > 1:
        fail(
            "plugin lookup ambiguous for "
            f"collector={reg['collector']}, collect_type={reg['collect_type']}, plugin_name={plugin_name}"
        )
    return plugins.first()


def resolve_single_node(instance, index):
    node_ids = instance.get("node_ids")
    if node_ids:
        return deepcopy(node_ids)

    node_name = instance.get("node_name") or defaults.get("node_name")
    node_ip = instance.get("node_ip") or defaults.get("node_ip")

    if node_name and node_ip:
        fail(f"instances[{index}] cannot provide both node_name and node_ip")

    if node_name:
        nodes = Node.objects.filter(name=node_name)
        count = nodes.count()
        if count == 0:
            fail(f"instances[{index}] node_name not found: {node_name}")
        if count > 1:
            fail(f"instances[{index}] node_name lookup ambiguous: {node_name}")
        return [nodes.first().id]

    if node_ip:
        nodes = Node.objects.filter(ip=node_ip)
        count = nodes.count()
        if count == 0:
            fail(f"instances[{index}] node_ip not found: {node_ip}")
        if count > 1:
            fail(f"instances[{index}] node_ip lookup ambiguous: {node_ip}")
        return [nodes.first().id]

    default_node_ids = defaults.get("node_ids") or []
    if default_node_ids:
        return deepcopy(default_node_ids)

    fail(f"instances[{index}] must provide node_ids, node_name, or node_ip")


monitor_object = resolve_monitor_object()
monitor_plugin = resolve_monitor_plugin()

if not monitor_plugin.monitor_object.filter(id=monitor_object.id).exists():
    fail(
        f"plugin '{monitor_plugin.name}' is not associated with monitor object '{monitor_object.name}'"
    )

request = {
    "monitor_object_id": monitor_object.id,
    "monitor_plugin_id": monitor_plugin.id,
    "collector": reg["collector"],
    "collect_type": reg["collect_type"],
    "configs": deepcopy(reg["configs"]),
    "instances": [],
}

default_group_ids = defaults.get("group_ids", [])
default_interval = defaults.get("interval")

for cfg in request["configs"]:
    if "interval" not in cfg and default_interval is not None:
        cfg["interval"] = default_interval

for index, item in enumerate(reg["instances"]):
    inst = deepcopy(item)
    if "group_ids" not in inst:
        inst["group_ids"] = deepcopy(default_group_ids)
    inst["node_ids"] = resolve_single_node(inst, index)
    if reg["collect_type"] == "host":
        inst["instance_type"] = "os"
        instance_id = str(inst.get("instance_id") or "").strip()
        if not instance_id:
            fail(
                f"instances[{index}].instance_id is required for host registrations; "
                "script will not generate synthetic cmd_* host instance ids"
            )
        inst["instance_id"] = instance_id
    inst.pop("install_agent", None)
    inst.pop("node_name", None)
    inst.pop("node_ip", None)
    if "interval" not in inst and default_interval is not None:
        inst["interval"] = default_interval
    request["instances"].append(inst)

with open(out_path, "w", encoding="utf-8") as f:
    yaml.safe_dump(request, f, allow_unicode=True, sort_keys=False)
PY
}

prepare_instances_with_node_ids() {
  local key="$1"
  local out="$2"

  MANIFEST_PATH="${MANIFEST_PATH}" REG_KEY="${key}" OUT_PATH="${out}" DEFAULT_NODEMGMT_WORK_NODE="${DEFAULT_NODEMGMT_WORK_NODE}" INSTALL_AGENT_TIMEOUT_SECONDS="${INSTALL_AGENT_TIMEOUT_SECONDS}" INSTALL_AGENT_POLL_INTERVAL_SECONDS="${INSTALL_AGENT_POLL_INTERVAL_SECONDS}" PYTHONPATH="${SERVER_DIR}:${SERVER_DIR}/..:${PYTHONPATH:-}" "${DJANGO_PYTHON}" <<'PY'
import os
import time
from copy import deepcopy
import yaml

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

import django

django.setup()

from apps.node_mgmt.models import Node, PackageVersion
from apps.node_mgmt.serializers.installer import ControllerInstallRequestSerializer
from apps.node_mgmt.services.installer import InstallerService
from apps.node_mgmt.tasks.installer import (
    install_controller,
    timeout_controller_install_task,
    CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
)

manifest_path = os.environ["MANIFEST_PATH"]
reg_key = os.environ["REG_KEY"]
out_path = os.environ["OUT_PATH"]
default_work_node = os.environ.get("DEFAULT_NODEMGMT_WORK_NODE", "default").strip() or "default"
timeout_seconds = int(os.environ.get("INSTALL_AGENT_TIMEOUT_SECONDS", "900"))
poll_interval_seconds = int(os.environ.get("INSTALL_AGENT_POLL_INTERVAL_SECONDS", "10"))


def fail(message: str):
    raise SystemExit(f"{reg_key}: {message}")


with open(manifest_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

defaults = data.get("defaults", {}) or {}
reg = deepcopy(next(item for item in data["registrations"] if item["key"] == reg_key))


def resolve_existing_node(instance):
    node_ids = instance.get("node_ids") or []
    if node_ids:
        nodes = Node.objects.filter(id__in=node_ids)
        count = nodes.count()
        if count == 1:
            return nodes.first()
        if count > 1:
            fail(f"node_ids lookup ambiguous: {node_ids}")

    node_name = instance.get("node_name") or defaults.get("node_name")
    if node_name:
        nodes = Node.objects.filter(name=node_name)
        count = nodes.count()
        if count == 1:
            return nodes.first()
        if count > 1:
            fail(f"node_name lookup ambiguous: {node_name}")

    node_ip = instance.get("node_ip") or defaults.get("node_ip")
    if node_ip:
        nodes = Node.objects.filter(ip=node_ip)
        count = nodes.count()
        if count == 1:
            return nodes.first()
        if count > 1:
            fail(f"node_ip lookup ambiguous: {node_ip}")

    host = instance.get("host")
    if host:
        nodes = Node.objects.filter(ip=host)
        if nodes.count() == 1:
            return nodes.first()

    return None


def validate_install_agent(instance):
    install = deepcopy(instance.get("install_agent") or {})
    if not install.get("enabled"):
        fail(f"node not found for host {instance.get('host')}, and install_agent credentials were not provided")

    auth_type = install.get("auth_type")
    if auth_type not in {"password", "private_key"}:
        fail("install_agent.auth_type must be password or private_key")
    if not install.get("username"):
        fail("install_agent.username is required")
    if auth_type == "password" and not install.get("password"):
        fail("install_agent.password is required when auth_type=password")
    if auth_type == "private_key" and not install.get("private_key"):
        fail("install_agent.private_key is required when auth_type=private_key")

    install.setdefault("port", 22)
    install.setdefault("os", "linux")
    if not install.get("cpu_architecture"):
        fail("install_agent.cpu_architecture is required")
    if install["os"] != "linux":
        fail("only linux install_agent is supported currently")
    if install.get("package_id") not in (None, ""):
        try:
            install["package_id"] = int(install["package_id"])
        except (TypeError, ValueError):
            fail("install_agent.package_id must be an integer when provided")
    if install.get("package_version") not in (None, ""):
        install["package_version"] = str(install["package_version"]).strip()
        if not install["package_version"]:
            fail("install_agent.package_version cannot be blank when provided")
    return install


def resolve_controller_package_id(install):
    explicit_package_id = install.get("package_id")
    if explicit_package_id:
        package = PackageVersion.objects.filter(
            id=explicit_package_id,
            type="controller",
            os="linux",
        ).first()
        if not package:
            fail(f"controller package_id not found: {explicit_package_id}")
        return package.id

    explicit_package_version = install.get("package_version")
    if explicit_package_version:
        package = PackageVersion.objects.filter(
            type="controller",
            os="linux",
            version=explicit_package_version,
            cpu_architecture=install.get("cpu_architecture", ""),
        ).order_by("-id").first()
        if not package:
            package = PackageVersion.objects.filter(
                type="controller",
                os="linux",
                version=explicit_package_version,
            ).order_by("-id").first()
        if not package:
            fail(f"controller package_version not found: {explicit_package_version}")
        return package.id

    package = PackageVersion.objects.filter(type="controller", os="linux", version="latest").order_by("-id").first()
    if package:
        return package.id
    package = PackageVersion.objects.filter(type="controller", os="linux").order_by("-id").first()
    if package:
        return package.id
    fail("no controller package version found for linux")


def start_install(instance, install):
    if not default_work_node:
        fail("DEFAULT_NODEMGMT_WORK_NODE is not configured")

    package_id = resolve_controller_package_id(install)
    host = instance.get("node_ip") or defaults.get("node_ip") or instance.get("host")
    if not host:
        fail("instance host is required for install_agent flow")

    group_ids = deepcopy(instance.get("group_ids") or defaults.get("group_ids") or [])
    node_name = install.get("node_name") or instance.get("node_name") or instance.get("instance_name") or host
    payload = {
        "cloud_region_id": 1,
        "work_node": default_work_node,
        "package_id": package_id,
        "cpu_architecture": install.get("cpu_architecture", ""),
        "nodes": [
            {
                "ip": host,
                "node_name": node_name,
                "os": install["os"],
                "organizations": group_ids,
                "port": int(install.get("port", 22)),
                "username": install["username"],
                "password": install.get("private_key") and "" or install.get("password", ""),
                "private_key": install.get("private_key", ""),
                "passphrase": install.get("passphrase", ""),
                "cpu_architecture": install.get("cpu_architecture", ""),
            }
        ],
    }
    serializer = ControllerInstallRequestSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    validated = serializer.validated_data

    task_id = InstallerService.install_controller(
        cloud_region_id=validated["cloud_region_id"],
        work_node=validated["work_node"],
        package_version_id=validated["package_id"],
        nodes=validated["nodes"],
        cpu_architecture=validated["cpu_architecture"],
    )
    install_controller.delay(task_id)
    timeout_controller_install_task.apply_async(
        args=[task_id],
        countdown=CONTROLLER_INSTALL_TASK_TIMEOUT_SECONDS,
    )
    return task_id

def wait_for_node(instance, existing_node_ids):
    host = instance.get("node_ip") or defaults.get("node_ip") or instance.get("host")
    if not host:
        fail("instance host is required to wait for node registration")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        nodes = Node.objects.filter(ip=host, cloud_region_id=1).exclude(id__in=existing_node_ids).order_by("-created_at", "-id")
        count = nodes.count()
        if count > 1:
            fail(f"multiple new nodes found after install for host {host} in cloud region 1")
        node = nodes.first()
        if node:
            return node
        time.sleep(poll_interval_seconds)
    fail(f"agent install started for host {host}, but node did not register back within {timeout_seconds} seconds")


for instance in reg.get("instances") or []:
    node = resolve_existing_node(instance)
    if node:
        install = instance.get("install_agent") or {}
        if install.get("enabled"):
            host = instance.get("node_ip") or defaults.get("node_ip") or instance.get("host") or node.ip
            print(f"{reg_key}: agent already installed for host {host}, skip install_agent")
    else:
        host = instance.get("node_ip") or defaults.get("node_ip") or instance.get("host")
        existing_node_ids = list(Node.objects.filter(ip=host, cloud_region_id=1).values_list("id", flat=True)) if host else []
        install = validate_install_agent(instance)
        start_install(instance, install)
        node = wait_for_node(instance, existing_node_ids)

    instance["node_ids"] = [node.id]

with open(out_path, "w", encoding="utf-8") as f:
    yaml.safe_dump({"defaults": defaults, "registration": reg}, f, allow_unicode=True, sort_keys=False)
PY
}

render_dashboard_yaml() {
  local out="$1"

  TEMPLATE_PATH="${TEMPLATE_DIR}/mysql_operation_analysis_dashboard.yaml.tpl" OUTPUT_PATH="${out}" python3 <<'PY'
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

run_create_monitor_instance() {
  local request_file="$1"
  local result_file="$2"

  (
    cd "${SERVER_DIR}"
    "${DJANGO_PYTHON}" manage.py create_monitor_instance \
      --config "${request_file}" \
      --output "${result_file}"
  )
}

is_existing_collect_config_failure() {
  local log_file="$1"

  [[ -f "${log_file}" ]] || return 1
  grep -qE '已存在采集配置，无法重复创建|冲突的配置类型=' "${log_file}"
}

build_existing_instance_result() {
  local request_file="$1"
  local result_file="$2"

REQUEST_FILE="${request_file}" RESULT_FILE="${result_file}" "${DJANGO_PYTHON}" <<'PY'
import ast
import os
import yaml

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
import django
django.setup()

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization
from apps.monitor.models.collect_config import CollectConfig


def extract_instance_id_values(raw_instance_id):
    if not raw_instance_id:
        return []
    if not isinstance(raw_instance_id, str):
        return [str(raw_instance_id)]
    if raw_instance_id.startswith("("):
        try:
            parsed = ast.literal_eval(raw_instance_id)
        except (SyntaxError, ValueError):
            return [raw_instance_id]
        if isinstance(parsed, tuple):
            return [str(item) for item in parsed]
    return [raw_instance_id]

with open(os.environ["REQUEST_FILE"], "r", encoding="utf-8") as f:
    request = yaml.safe_load(f) or {}

monitor_object_id = request.get("monitor_object_id")
instances_out = []
for inst in request.get("instances") or []:
    instance_name = inst.get("instance_name")
    if not instance_name:
        raise SystemExit("existing monitor instance lookup requires instance_name")

    monitor_instance = (
        MonitorInstance.objects.select_related("monitor_object")
        .filter(name=instance_name, monitor_object_id=monitor_object_id)
        .first()
    )
    if not monitor_instance:
        raise SystemExit(
            f"existing monitor instance not found for instance_name={instance_name}, monitor_object_id={monitor_object_id}"
        )

    instance_id = monitor_instance.id

    orgs = list(
        MonitorInstanceOrganization.objects.filter(monitor_instance_id=instance_id).values_list("organization", flat=True)
    )
    configs = []
    for cfg in CollectConfig.objects.filter(monitor_instance_id=instance_id):
        configs.append(
            {
                "id": cfg.id,
                "collector": cfg.collector,
                "collect_type": cfg.collect_type,
                "config_type": cfg.config_type,
                "monitor_plugin_id": cfg.monitor_plugin_id,
                "is_child": cfg.is_child,
            }
        )

    instances_out.append(
        {
            "instance_id": monitor_instance.id,
            "instance_id_values": extract_instance_id_values(monitor_instance.id),
            "instance_name": monitor_instance.name,
            "monitor_object_id": monitor_instance.monitor_object_id,
            "monitor_object_name": monitor_instance.monitor_object.name,
            "organizations": orgs,
            "interval": getattr(monitor_instance, "interval", 10),
            "is_active": True,
            "is_deleted": monitor_instance.is_deleted,
            "auto": monitor_instance.auto,
            "configs": configs,
            "created_at": monitor_instance.created_at.isoformat() if monitor_instance.created_at else None,
            "updated_at": monitor_instance.updated_at.isoformat() if monitor_instance.updated_at else None,
        }
    )

result = {
    "request": request,
    "result": {
        "status": "success",
        "instances": instances_out,
    },
}

with open(os.environ["RESULT_FILE"], "w", encoding="utf-8") as f:
    yaml.safe_dump(result, f, allow_unicode=True, sort_keys=False)
PY
}

finalize_registration_success() {
  local key="$1"
  local request_file="$2"
  local result_file="$3"
  local meta_file="$4"
  local oa_widget_file="$5"

  local ids
  local alarm_status
  local alarm_error
  local oa_status
  local oa_error

  ids="$(extract_instance_ids "${result_file}" | paste -sd, -)"
  alarm_status="skipped"
  alarm_error=""
  if run_alarm_policy_post_step "${key}" "${result_file}"; then
    alarm_status="success"
  else
    rc=$?
    if [[ ${rc} -eq 2 ]]; then
      alarm_status="skipped"
    else
      alarm_status="failed"
      alarm_error="alarm policy step failed"
    fi
  fi
  oa_status="skipped"
  oa_error=""
  if queue_operation_analysis_widget "${key}" "${result_file}" "${oa_widget_file}"; then
    oa_status="queued"
  else
    rc=$?
    if [[ ${rc} -eq 2 ]]; then
      oa_status="skipped"
    else
      oa_status="failed"
      oa_error="operation_analysis step failed"
    fi
  fi
  {
    printf 'key: %s\n' "${key}"
    printf 'status: success\n'
    printf 'request_file: %s\n' "${request_file}"
    printf 'result_file: %s\n' "${result_file}"
    printf 'instance_ids:\n'
    if [[ -n "${ids}" ]]; then
      for id in ${ids//,/ }; do
        printf '  - %s\n' "${id}"
      done
    fi
    printf 'alarm_policies:\n'
    printf '  status: %s\n' "${alarm_status}"
    if [[ -n "${alarm_error}" ]]; then
      printf '  error: %s\n' "${alarm_error}"
    fi
    printf 'operation_analysis:\n'
    printf '  status: %s\n' "${oa_status}"
    if [[ -n "${oa_error}" ]]; then
      printf '  error: %s\n' "${oa_error}"
    fi
  } > "${meta_file}"
  log "registration succeeded: ${key}"
}

extract_instance_ids() {
  local result_file="$1"

  RESULT_FILE="${result_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["RESULT_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

for item in ((data.get("result") or {}).get("instances") or []):
    for val in item.get("instance_id_values") or []:
        print(val)
PY
}

extract_first_instance_label() {
  local result_file="$1"

  RESULT_FILE="${result_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import sys
import yaml

with open(os.environ["RESULT_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

instances = ((data.get("result") or {}).get("instances") or [])
if not instances:
    sys.exit(1)
labels = instances[0].get("instance_id_values") or []
if not labels:
    sys.exit(1)
print(labels[0])
PY
}

probe_metric_once() {
  OA_QUERY_EXPR="${OA_QUERY_EXPR}" OA_QUERY_STEP="${OA_QUERY_STEP}" METRIC_READY_LOOKBACK_SECONDS="${METRIC_READY_LOOKBACK_SECONDS}" SERVER_DIR="${SERVER_DIR}" \
  "${DJANGO_PYTHON}" <<'PY'
import os
import sys
import time
from requests.exceptions import MissingSchema
from dotenv import load_dotenv

load_dotenv(os.path.join(os.environ["SERVER_DIR"], ".env"))

from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

query = os.environ["OA_QUERY_EXPR"]
step = os.environ["OA_QUERY_STEP"]
lookback = int(os.environ["METRIC_READY_LOOKBACK_SECONDS"])
end_ts = int(time.time())
start_ts = end_ts - lookback
vm_host = os.getenv("VICTORIAMETRICS_HOST")
if not vm_host:
    print("config_error: VICTORIAMETRICS_HOST is not set", file=sys.stderr)
    sys.exit(2)

try:
    resp = VictoriaMetricsAPI().query_range(query, start_ts, end_ts, step)
except MissingSchema as exc:
    print(f"config_error: invalid VictoriaMetrics host: {exc}", file=sys.stderr)
    sys.exit(2)
except Exception as exc:
    print(f"probe_error: {exc}", file=sys.stderr)
    sys.exit(1)

result = (((resp or {}).get("data") or {}).get("result")) or []
has_values = any(item.get("values") for item in result)
print("ready" if has_values else "not_ready")
sys.exit(0 if has_values else 1)
PY
}

wait_metric_ready() {
  local attempt=1
  local probe_output
  local probe_rc
  while (( attempt <= METRIC_READY_RETRIES )); do
    probe_output="$(probe_metric_once 2>&1)"
    probe_rc=$?
    if [[ ${probe_rc} -eq 0 ]]; then
      log "metric ready on attempt ${attempt}/${METRIC_READY_RETRIES}"
      return 0
    fi
    if [[ ${probe_rc} -eq 2 ]]; then
      log "metric readiness check failed: ${probe_output}"
      return 2
    fi
    log "metric not ready yet, retry ${attempt}/${METRIC_READY_RETRIES}"
    sleep "${METRIC_READY_INTERVAL_SECONDS}"
    attempt=$((attempt + 1))
  done
  return 1
}

load_registration_oa_env() {
  local key="$1"

  MANIFEST_PATH="${MANIFEST_PATH}" REG_KEY="${key}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["MANIFEST_PATH"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

defaults = data.get("defaults", {}) or {}
oa_defaults = defaults.get("oa", {}) or {}
reg = next(item for item in data["registrations"] if item["key"] == os.environ["REG_KEY"])
oa = oa_defaults | (reg.get("operation_analysis") or {})
oa_raw = reg.get("operation_analysis") or {}

for key, value in {
    "OA_ENABLED": str(bool(oa.get("enabled", False))).lower(),
    "OA_DASHBOARD_KEY": oa.get("dashboard_key", reg["key"]),
    "OA_TARGET_DIRECTORY_ID": oa.get("target_directory_id", ""),
    "OA_DASHBOARD_NAME": oa.get("dashboard_name", f"{reg['key']}-dashboard"),
    "OA_DASHBOARD_DESC": oa.get("dashboard_desc", "Auto-created from monitor manifest"),
    "OA_EXISTING_DATASOURCE_NAME": oa.get("datasource_name", "查询时间范围内的指标数据"),
    "OA_EXISTING_DATASOURCE_REST_API": oa.get("datasource_rest_api", "monitor/mm_query_range"),
    "OA_CREATED_BY": oa.get("created_by", "admin"),
    "OA_QUERY_METRIC": oa.get("query_metric", "mysql_threads_connected"),
    "OA_QUERY_EXPR": oa.get("query_expr", ""),
    "OA_QUERY_STEP": oa.get("query_step", "5m"),
    "OA_QUERY_TIME_RANGE": oa.get("query_time_range", 10080),
    "OA_WIDGET_ID": oa.get("widget_id", "mysql-monitor-widget"),
    "OA_WIDGET_TITLE": oa.get("widget_title", "MySQL 指标趋势"),
    "OA_WIDGET_DESC": oa.get("widget_desc", ""),
    "OA_WIDGET_X": oa.get("widget_x", 0),
    "OA_WIDGET_Y": oa.get("widget_y", 0),
    "OA_WIDGET_W": oa.get("widget_w", 6),
    "OA_WIDGET_H": oa.get("widget_h", 4),
    "OA_CHART_TYPE": oa.get("chart_type", "line"),
    "OA_WIDGET_X_EXPLICIT": str("widget_x" in oa_raw).lower(),
    "OA_WIDGET_Y_EXPLICIT": str("widget_y" in oa_raw).lower(),
}.items():
    print(f"declare -x {key}={value!r}")
PY
}

write_oa_widget_spec() {
  local widget_file="$1"

  WIDGET_FILE="${widget_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

doc = {
    "dashboard_key": os.environ["OA_DASHBOARD_KEY"],
    "registration_key": os.environ["OA_REGISTRATION_KEY"],
    "target_directory_id": int(os.environ["OA_TARGET_DIRECTORY_ID"]),
    "dashboard_name": os.environ["OA_DASHBOARD_NAME"],
    "dashboard_desc": os.environ["OA_DASHBOARD_DESC"],
    "datasource_name": os.environ["OA_EXISTING_DATASOURCE_NAME"],
    "datasource_rest_api": os.environ["OA_EXISTING_DATASOURCE_REST_API"],
    "created_by": os.environ["OA_CREATED_BY"],
    "group_id": int(os.environ["MYSQL_GROUP_ID"]),
    "widget": {
        "i": os.environ["OA_WIDGET_ID"],
        "x": int(os.environ["OA_WIDGET_X"]),
        "y": int(os.environ["OA_WIDGET_Y"]),
        "w": int(os.environ["OA_WIDGET_W"]),
        "h": int(os.environ["OA_WIDGET_H"]),
        "name": os.environ["OA_WIDGET_TITLE"],
        "description": os.environ["OA_WIDGET_DESC"],
        "valueConfig": {
            "chartType": os.environ["OA_CHART_TYPE"],
            "dataSource": os.environ["OA_DATASOURCE_KEY"],
            "dataSourceParams": [
                {
                    "name": "query",
                    "type": "string",
                    "value": os.environ["OA_QUERY_EXPR"],
                    "alias_name": "query",
                    "filterType": "params",
                },
                {
                    "name": "time_range",
                    "type": "timeRange",
                    "value": int(os.environ["OA_QUERY_TIME_RANGE"]),
                    "alias_name": "time_range",
                    "filterType": "fixed",
                },
                {
                    "name": "step",
                    "type": "string",
                    "value": os.environ["OA_QUERY_STEP"],
                    "alias_name": "step",
                    "filterType": "params",
                },
            ],
        },
    },
    "widget_x_explicit": os.environ["OA_WIDGET_X_EXPLICIT"] == "true",
    "widget_y_explicit": os.environ["OA_WIDGET_Y_EXPLICIT"] == "true",
}

with open(os.environ["WIDGET_FILE"], "w", encoding="utf-8") as f:
    yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
PY
}

queue_operation_analysis_widget() {
  local key="$1"
  local result_file="$2"
  local widget_file="$3"

  local env_lines
  env_lines="$(load_registration_oa_env "${key}")"
  while IFS= read -r line; do
    eval "${line}"
  done <<< "${env_lines}"

  if [[ "${OA_ENABLED}" != "true" ]]; then
    return 2
  fi

  INSTANCE_LABEL="$(extract_first_instance_label "${result_file}")" || return 1
  if [[ -z "${OA_QUERY_EXPR}" ]]; then
    if [[ -z "${OA_QUERY_METRIC}" ]]; then
      return 1
    fi
    OA_QUERY_EXPR="${OA_QUERY_METRIC}{instance_id=\"${INSTANCE_LABEL}\"}"
  fi
  OA_DATASOURCE_KEY="${OA_EXISTING_DATASOURCE_NAME}::${OA_EXISTING_DATASOURCE_REST_API}"
  OA_REGISTRATION_KEY="${key}"

  export OA_QUERY_EXPR OA_QUERY_STEP OA_QUERY_TIME_RANGE OA_WIDGET_ID OA_WIDGET_TITLE OA_WIDGET_DESC OA_WIDGET_X OA_WIDGET_Y OA_WIDGET_W OA_WIDGET_H OA_CHART_TYPE OA_DASHBOARD_NAME OA_DASHBOARD_DESC OA_DATASOURCE_KEY
  export OA_EXISTING_DATASOURCE_NAME OA_EXISTING_DATASOURCE_REST_API OA_CREATED_BY OA_TARGET_DIRECTORY_ID INSTANCE_LABEL OA_DASHBOARD_KEY OA_REGISTRATION_KEY OA_WIDGET_X_EXPLICIT OA_WIDGET_Y_EXPLICIT

  log "waiting metric for operation_analysis: ${key}"
  wait_metric_ready || return 1
  write_oa_widget_spec "${widget_file}"
}

build_oa_group_files() {
  local manifest_group_dir="$1"

  MANIFEST_PATH="${MANIFEST_PATH}" OUTPUT_DIR="${OUTPUT_DIR}" OA_GROUP_DIR="${manifest_group_dir}" "${DJANGO_PYTHON}" <<'PY'
import os
from pathlib import Path
import yaml

with open(os.environ["MANIFEST_PATH"], "r", encoding="utf-8") as f:
    manifest = yaml.safe_load(f) or {}

output_dir = Path(os.environ["OUTPUT_DIR"])
group_dir = Path(os.environ["OA_GROUP_DIR"])
group_dir.mkdir(parents=True, exist_ok=True)

grouped = {}
for path in sorted(output_dir.glob("*.oa-widget.yaml")):
    with open(path, "r", encoding="utf-8") as f:
        item = yaml.safe_load(f) or {}
    grouped.setdefault(item["dashboard_key"], []).append(item)

expected = {}
oa_defaults = (manifest.get("defaults") or {}).get("oa") or {}
for reg in manifest.get("registrations") or []:
    oa = oa_defaults | ((reg.get("operation_analysis") or {}))
    if not oa.get("enabled"):
        continue
    dashboard_key = oa.get("dashboard_key", reg.get("key"))
    expected.setdefault(dashboard_key, []).append(reg.get("key"))

for index, (dashboard_key, items) in enumerate(grouped.items(), start=1):
    first = items[0]
    for pos, item in enumerate(items):
        widget = item["widget"]
        if not item.get("widget_x_explicit"):
            widget["x"] = 0 if pos % 2 == 0 else int(widget.get("w", 6))
        if not item.get("widget_y_explicit"):
            widget["y"] = (pos // 2) * int(widget.get("h", 4))
    doc = {
        "dashboard_key": dashboard_key,
        "target_directory_id": first["target_directory_id"],
        "dashboard_name": first["dashboard_name"],
        "dashboard_desc": first["dashboard_desc"],
        "datasource_name": first["datasource_name"],
        "datasource_rest_api": first["datasource_rest_api"],
        "created_by": first["created_by"],
        "group_id": first["group_id"],
        "registrations": [item["registration_key"] for item in items],
        "expected_registrations": expected.get(dashboard_key, []),
        "widgets": [item["widget"] for item in items],
    }
    out_path = group_dir / f"group-{index:03d}.yaml"
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
PY
}

load_group_oa_env() {
  local group_file="$1"

  GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

for key, value in {
    "OA_DASHBOARD_KEY": data.get("dashboard_key", ""),
    "OA_TARGET_DIRECTORY_ID": data.get("target_directory_id", ""),
    "OA_DASHBOARD_NAME": data.get("dashboard_name", ""),
    "OA_DASHBOARD_DESC": data.get("dashboard_desc", ""),
    "OA_EXISTING_DATASOURCE_NAME": data.get("datasource_name", ""),
    "OA_EXISTING_DATASOURCE_REST_API": data.get("datasource_rest_api", ""),
    "OA_CREATED_BY": data.get("created_by", "admin"),
    "MYSQL_GROUP_ID": data.get("group_id", 1),
}.items():
    print(f"declare -x {key}={value!r}")
PY
}

build_view_sets_yaml() {
  local group_file="$1"

  GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

rendered = yaml.safe_dump(data.get("widgets") or [], allow_unicode=True, sort_keys=False).rstrip()
for line in rendered.splitlines():
    print(f"      {line}")
PY
}

update_meta_oa_status() {
  local key="$1"
  local status="$2"
  local error="${3:-}"

  META_FILE="${OUTPUT_DIR}/${key}.meta.yaml" OA_STATUS="${status}" OA_ERROR="${error}" "${DJANGO_PYTHON}" <<'PY'
import os
from pathlib import Path
import yaml

path = os.environ["META_FILE"]
meta_path = Path(path)
if meta_path.exists():
    with meta_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
else:
    key = meta_path.name.removesuffix(".meta.yaml")
    data = {
        "key": key,
        "status": "pending",
    }

data.setdefault("operation_analysis", {})
data["operation_analysis"]["status"] = os.environ["OA_STATUS"]
if os.environ.get("OA_ERROR"):
    data["operation_analysis"]["error"] = os.environ["OA_ERROR"]
else:
    data["operation_analysis"].pop("error", None)

with meta_path.open("w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
PY
}

extract_registration_instance_context() {
  local result_file="$1"
  local out_file="$2"

  RESULT_FILE="${result_file}" OUT_FILE="${out_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["RESULT_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

instances = ((data.get("result") or {}).get("instances") or [])

doc = {"instances": []}
for item in instances:
    doc["instances"].append(
        {
            "instance_name": item.get("instance_name"),
            "instance_id_values": item.get("instance_id_values") or [],
        }
    )

with open(os.environ["OUT_FILE"], "w", encoding="utf-8") as f:
    yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
PY
}

build_alarm_policy_specs() {
  local key="$1"
  local instance_ctx_file="$2"
  local out_file="$3"

  MANIFEST_PATH="${MANIFEST_PATH}" REG_KEY="${key}" INSTANCE_CTX_FILE="${instance_ctx_file}" OUT_FILE="${out_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml
from copy import deepcopy

with open(os.environ["MANIFEST_PATH"], "r", encoding="utf-8") as f:
    manifest = yaml.safe_load(f) or {}

with open(os.environ["INSTANCE_CTX_FILE"], "r", encoding="utf-8") as f:
    instance_ctx = yaml.safe_load(f) or {}

reg = next(item for item in manifest["registrations"] if item["key"] == os.environ["REG_KEY"])
alarm_policies = reg.get("alarm_policies") or []

UNIT_MAP = {
    "minute": "min",
    "minutes": "min",
    "min": "min",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "days": "day",
}


def normalize_time_block(block):
    block = deepcopy(block or {})
    if "type" in block:
        return block
    unit = block.get("unit")
    if unit:
        mapped = UNIT_MAP.get(unit)
        if mapped:
            block["type"] = mapped
            block.pop("unit", None)
    return block

doc = {
    "registration_key": reg["key"],
    "monitor_object_name": reg.get("monitor_object_name"),
    "collect_type": reg.get("collect_type"),
    "organizations": reg.get("organizations") or manifest.get("defaults", {}).get("group_ids") or [],
    "policies": [],
}

instance_items = instance_ctx.get("instances") or []
for item in alarm_policies:
    spec = deepcopy(item)
    spec["schedule"] = normalize_time_block(spec.get("schedule"))
    spec["period"] = normalize_time_block(spec.get("period"))
    if spec.get("no_data_period"):
        spec["no_data_period"] = normalize_time_block(spec.get("no_data_period"))
    if spec.get("no_data_recovery_period"):
        spec["no_data_recovery_period"] = normalize_time_block(spec.get("no_data_recovery_period"))
    source = spec.get("source") or {}
    if source.get("from_registration_instances") is True:
        spec["source"] = {
            "values": [
                {
                    "instance_name": inst.get("instance_name"),
                    "instance_id_values": inst.get("instance_id_values") or [],
                }
                for inst in instance_items
            ]
        }
    doc["policies"].append(spec)

with open(os.environ["OUT_FILE"], "w", encoding="utf-8") as f:
    yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
PY
}

apply_alarm_policies_via_django() {
  local policy_file="$1"

  POLICY_FILE="${policy_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
import django
django.setup()

from rest_framework.test import APIRequestFactory

from apps.monitor.models.monitor_policy import MonitorPolicy
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import PolicyOrganization
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

with open(os.environ["POLICY_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

monitor_object = MonitorObject.objects.get(name=data["monitor_object_name"])
operator = "admin"
applied = []

factory = APIRequestFactory()
fake_request = factory.post("/api/monitor_policy/")
fake_request.user = type("User", (), {"username": operator})()
view = MonitorPolicyViewSet()

for item in data.get("policies") or []:
    existing = MonitorPolicy.objects.filter(
        monitor_object=monitor_object,
        name=item["name"],
        collect_type=item["collect_type"],
    ).first()

    payload = {
        "monitor_object": monitor_object.id,
        "name": item["name"],
        "organizations": item.get("organizations", data.get("organizations") or []),
        "alert_name": item["alert_name"],
        "collect_type": item["collect_type"],
        "query_condition": item["query_condition"],
        "source": item["source"],
        "schedule": item["schedule"],
        "period": item["period"],
        "algorithm": item["algorithm"],
        "group_by": item.get("group_by", []),
        "threshold": item["threshold"],
        "recovery_condition": item.get("recovery_condition", 1),
        "metric_unit": item.get("metric_unit", ""),
        "calculation_unit": item.get("calculation_unit", ""),
        "no_data_period": item.get("no_data_period", {}),
        "no_data_level": item.get("no_data_level", "warning"),
        "no_data_alert_name": item.get("no_data_alert_name", f"{item['alert_name']}-no-data"),
        "no_data_recovery_period": item.get("no_data_recovery_period", {}),
        "notice": item.get("notice", True),
        "notice_type": item.get("notice_type", ""),
        "notice_type_id": item.get("notice_type_id", 0),
        "notice_users": item.get("notice_users", []),
        "enable": item.get("enable", True),
        "enable_alerts": item.get("enable_alerts", []),
        "updated_by": operator,
    }

    if existing:
        serializer = MonitorPolicySerializer(existing, data=payload, partial=False)
    else:
        payload["created_by"] = operator
        serializer = MonitorPolicySerializer(data=payload)

    serializer.is_valid(raise_exception=True)
    obj = serializer.save()

    view.update_or_create_task(obj.id, payload["schedule"])
    view.update_policy_organizations(obj.id, payload["organizations"])
    if existing:
        old_enable = existing.enable
        old_state = view.get_baseline_state(existing)
        refreshed = MonitorPolicy.objects.filter(id=obj.id).first()
        if view.should_update_policy_baselines(existing, old_state, refreshed):
            view.update_policy_baselines(
                obj.id,
                refreshed.enable_alerts,
                operator=operator,
                reset_active_no_data_alerts=view.baseline_state_changed(old_state, refreshed),
            )
        if payload.get("enable") != old_enable:
            view.handle_policy_enable_change(obj.id, old_enable, payload.get("enable"))
    else:
        created = MonitorPolicy.objects.filter(id=obj.id).first()
        if view.is_no_data_alert_enabled(created):
            view.update_policy_baselines(obj.id, created.enable_alerts, operator=operator)

    applied.append(
        {
            "policy_key": item["policy_key"],
            "policy_id": obj.id,
            "name": obj.name,
        }
    )

print(yaml.safe_dump({"applied": applied}, allow_unicode=True, sort_keys=False))
PY
}

update_meta_alarm_policy_status() {
  local key="$1"
  local status="$2"
  local applied_file="${3:-}"
  local error="${4:-}"

  META_FILE="${OUTPUT_DIR}/${key}.meta.yaml" STATUS="${status}" APPLIED_FILE="${applied_file}" ERROR_MSG="${error}" "${DJANGO_PYTHON}" <<'PY'
import os
from pathlib import Path
import yaml

meta_file = os.environ["META_FILE"]
status = os.environ["STATUS"]
applied_file = os.environ.get("APPLIED_FILE", "")
error_msg = os.environ.get("ERROR_MSG", "")

meta_path = Path(meta_file)
if meta_path.exists():
    with meta_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
else:
    key = meta_path.name.removesuffix(".meta.yaml")
    data = {
        "key": key,
        "status": "pending",
    }

data.setdefault("alarm_policies", {})
data["alarm_policies"]["status"] = status

if applied_file and os.path.exists(applied_file):
    with open(applied_file, "r", encoding="utf-8") as f:
        applied = yaml.safe_load(f) or {}
    data["alarm_policies"]["applied"] = applied.get("applied", [])

if error_msg:
    data["alarm_policies"]["error"] = error_msg
else:
    data["alarm_policies"].pop("error", None)

with meta_path.open("w", encoding="utf-8") as f:
    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
PY
}

run_alarm_policy_post_step() {
  local key="$1"
  local result_file="$2"

  local policy_ctx_file="${OUTPUT_DIR}/${key}.alarm-policy-instance-context.yaml"
  local policy_spec_file="${OUTPUT_DIR}/${key}.alarm-policies.yaml"
  local policy_apply_file="${OUTPUT_DIR}/${key}.alarm-policies.applied.yaml"

  if ! MANIFEST_PATH="${MANIFEST_PATH}" REG_KEY="${key}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["MANIFEST_PATH"], "r", encoding="utf-8") as f:
    manifest = yaml.safe_load(f) or {}

reg = next(item for item in manifest.get("registrations", []) if item.get("key") == os.environ["REG_KEY"])
raise SystemExit(0 if (reg.get("alarm_policies") or []) else 1)
PY
  then
    return 2
  fi

  extract_registration_instance_context "${result_file}" "${policy_ctx_file}"
  build_alarm_policy_specs "${key}" "${policy_ctx_file}" "${policy_spec_file}"

  if apply_alarm_policies_via_django "${policy_spec_file}" > "${policy_apply_file}"; then
    update_meta_alarm_policy_status "${key}" "success" "${policy_apply_file}"
    return 0
  fi

  update_meta_alarm_policy_status "${key}" "failed" "" "alarm policy step failed"
  return 1
}

process_operation_analysis_groups() {
  build_oa_group_files "${OA_GROUP_DIR}"

  local group_file
  while IFS= read -r group_file; do
    [[ -n "${group_file}" ]] || continue

    local env_lines
    env_lines="$(load_group_oa_env "${group_file}")"
    while IFS= read -r line; do
      eval "${line}"
    done <<< "${env_lines}"

    local reg_key
    while IFS= read -r reg_key; do
      [[ -n "${reg_key}" ]] && update_meta_oa_status "${reg_key}" "failed" "operation_analysis group incomplete"
    done < <(GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

expected = set(data.get("expected_registrations") or [])
actual = set(data.get("registrations") or [])
if expected != actual:
    for key in sorted(expected):
        print(key)
PY
)

    if GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY'
import os
import sys
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

expected = set(data.get("expected_registrations") or [])
actual = set(data.get("registrations") or [])
sys.exit(0 if expected == actual else 1)
PY
    then
      :
    else
      continue
    fi

    OA_DATASOURCE_KEY="${OA_EXISTING_DATASOURCE_NAME}::${OA_EXISTING_DATASOURCE_REST_API}"
    OA_VIEW_SETS_YAML="$(build_view_sets_yaml "${group_file}")"
    local oa_yaml_file="${group_file%.yaml}.dashboard.yaml"

    export OA_DASHBOARD_NAME OA_DASHBOARD_DESC OA_DATASOURCE_KEY OA_VIEW_SETS_YAML
    export OA_EXISTING_DATASOURCE_NAME OA_EXISTING_DATASOURCE_REST_API OA_CREATED_BY OA_TARGET_DIRECTORY_ID MYSQL_GROUP_ID

    if render_dashboard_yaml "${oa_yaml_file}" && apply_oa_dashboard_via_django "${oa_yaml_file}"; then
      GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY' | while IFS= read -r reg_key; do
import os
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

for key in data.get("registrations") or []:
    print(key)
PY
        [[ -n "${reg_key}" ]] && update_meta_oa_status "${reg_key}" "success"
      done
    else
      GROUP_FILE="${group_file}" "${DJANGO_PYTHON}" <<'PY' | while IFS= read -r reg_key; do
import os
import yaml

with open(os.environ["GROUP_FILE"], "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

for key in data.get("registrations") or []:
    print(key)
PY
        [[ -n "${reg_key}" ]] && update_meta_oa_status "${reg_key}" "failed" "operation_analysis step failed"
      done
    fi
  done < <(find "${OA_GROUP_DIR}" -type f -name 'group-*.yaml' | sort)
}

apply_oa_dashboard_via_django() {
  local oa_yaml="$1"

  (
    cd "${SERVER_DIR}"
    OA_IMPORT_YAML="${oa_yaml}" \
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

dashboard = Dashboard.objects.filter(name=dashboard_item["name"], directory=directory).first()
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
  )
}

write_summary() {
  OUTPUT_DIR="${OUTPUT_DIR}" SUMMARY_FILE="${SUMMARY_FILE}" "${DJANGO_PYTHON}" <<'PY'
import os
from pathlib import Path
import yaml

output_dir = Path(os.environ["OUTPUT_DIR"])
summary_file = Path(os.environ["SUMMARY_FILE"])
result_files = sorted(output_dir.glob("*.meta.yaml"))

results = []
success = 0
failed = 0

for path in result_files:
    with open(path, "r", encoding="utf-8") as f:
        item = yaml.safe_load(f) or {}
    results.append(item)
    oa_failed = ((item.get("operation_analysis") or {}).get("status") == "failed")
    alarm_failed = ((item.get("alarm_policies") or {}).get("status") == "failed")
    if item.get("status") == "success" and not oa_failed and not alarm_failed:
        success += 1
    else:
        failed += 1

doc = {
    "status": "success" if failed == 0 else ("failed" if success == 0 else "partial_success"),
    "summary": {
        "total": len(results),
        "success": success,
        "failed": failed,
    },
    "results": results,
}

with open(summary_file, "w", encoding="utf-8") as f:
    yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
PY
}

main() {
  check_env
  validate_manifest

  log "using manifest: ${MANIFEST_PATH}"
  log "output dir: ${OUTPUT_DIR}"

  while IFS= read -r key; do
    prepared_reg_file="${OUTPUT_DIR}/${key}.prepared-registration.yaml"
    request_file="${OUTPUT_DIR}/${key}.request.yaml"
    result_file="${OUTPUT_DIR}/${key}.result.yaml"
    meta_file="${OUTPUT_DIR}/${key}.meta.yaml"
    oa_widget_file="${OUTPUT_DIR}/${key}.oa-widget.yaml"
    create_log_file="${OUTPUT_DIR}/${key}.create-monitor-instance.log"

    log "processing registration: ${key}"
    prepare_instances_with_node_ids "${key}" "${prepared_reg_file}"
    render_request_yaml "${prepared_reg_file}" "${request_file}"

    if run_create_monitor_instance "${request_file}" "${result_file}" >"${create_log_file}" 2>&1; then
      finalize_registration_success "${key}" "${request_file}" "${result_file}" "${meta_file}" "${oa_widget_file}"
    else
      cat "${create_log_file}" >&2 || true
      if is_existing_collect_config_failure "${create_log_file}" && build_existing_instance_result "${request_file}" "${result_file}"; then
        log "existing collect config detected for ${key}, reused existing monitor instance"
        finalize_registration_success "${key}" "${request_file}" "${result_file}" "${meta_file}" "${oa_widget_file}"
      else
        {
          printf 'key: %s\n' "${key}"
          printf 'status: failed\n'
          printf 'request_file: %s\n' "${request_file}"
          printf 'result_file: %s\n' "${result_file}"
          printf 'error: create_monitor_instance failed\n'
        } > "${meta_file}"
        log "registration failed: ${key}"
      fi
    fi
  done < <(list_registration_keys)

  process_operation_analysis_groups

  write_summary
  log "summary written: ${SUMMARY_FILE}"
}

main "$@"

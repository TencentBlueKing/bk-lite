#!/bin/bash

# webhookd infra render script
# 接收 JSON: {"cluster_name": "xxx", "type": "metric|log|resource", "nats_url": "nats://x.x.x.x:4222", "nats_username": "user", "nats_password": "pass", "nats_ca": "...", "image_registry_prefix": "bk-lite.tencentcloudcr.com/bklite", "runtime_profile": "standard|docker|custom", "host_log_path": "/var/log/pods", "docker_container_log_path": "/var/lib/docker/containers", "namespace_patterns": [], "pod_patterns": []}
# 渲染出 K8s 配置 YAML
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBHOOKD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-log-collector.yaml")
METRIC_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-metric-collector.yaml")
RESOURCE_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-resource-collector.yaml")
SECRET_TEMPLATE=$(cat <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: bk-lite-monitor-config-secret
  namespace: bk-lite-collector
type: Opaque
data:
  CLUSTER_NAME: ${CLUSTER_NAME_BASE64}
  NATS_URL: ${NATS_URL_BASE64}
  NATS_USERNAME: ${NATS_USERNAME_BASE64}
  NATS_PASSWORD: ${NATS_PASSWORD_BASE64}
  ca.crt: ${NATS_CA_BASE64}
EOF
)

# 返回成功的 JSON 响应（支持多行内容）
json_success() {
    local id="$1"
    local message="$2"
    shift 2
    
    # 使用 jq 构建 JSON，确保正确转义
    local json
    json=$(jq -n --arg id "$id" --arg message "$message" '{status: "success", id: $id, message: $message}')
    
    # 添加额外的字段
    while [ $# -gt 0 ]; do
        json=$(echo "$json" | jq --arg key "$1" --arg value "$2" '. + {($key): $value}')
        shift 2
    done
    
    echo "$json"
}

# 返回错误的 JSON 响应
json_error() {
    local id="$1"
    local message="$2"
    local error="${3:-}"
    
    if [ -n "$error" ]; then
        jq -n --arg id "$id" --arg message "$message" --arg error "$error" \
            '{status: "error", id: $id, message: $message, error: $error}'
    else
        jq -n --arg id "$id" --arg message "$message" \
            '{status: "error", id: $id, message: $message}'
    fi
}

# load template files


# NATS 配置文件存储目录
NATS_DIR="${NATS_DIR:-/opt/webhookd/nats}"

# 获取 JSON 数据：优先从 $1 参数获取，否则从标准输入读取
JSON_DATA="${1:-$(cat)}"

[ -z "$JSON_DATA" ] && { json_error "" "No JSON data provided"; exit 1; }

# 提取参数
CLUSTER_NAME=$(echo "$JSON_DATA" | jq -r '.cluster_name // empty')
TYPE=$(echo "$JSON_DATA" | jq -r '.type // empty')
NATS_URL=$(echo "$JSON_DATA" | jq -r '.nats_url // empty')
NATS_USERNAME=$(echo "$JSON_DATA" | jq -r '.nats_username // empty')
NATS_PASSWORD=$(echo "$JSON_DATA" | jq -r '.nats_password // empty')
NATS_CA=$(echo "$JSON_DATA" | jq -r '.nats_ca // empty')
RUNTIME_PROFILE=$(echo "$JSON_DATA" | jq -r '.runtime_profile // "standard"')
HOST_LOG_PATH=$(echo "$JSON_DATA" | jq -r '.host_log_path // empty')
DOCKER_CONTAINER_LOG_PATH=$(echo "$JSON_DATA" | jq -r '.docker_container_log_path // empty')
NAMESPACE_PATTERNS=$(echo "$JSON_DATA" | jq -c '.namespace_patterns // []')
POD_PATTERNS=$(echo "$JSON_DATA" | jq -c '.pod_patterns // []')
IMAGE_REGISTRY_PREFIX=$(echo "$JSON_DATA" | jq -r '.image_registry_prefix // "bk-lite.tencentcloudcr.com/bklite"')

# 验证必填字段
validate_cluster_name() {
    [[ "$1" =~ ^[a-zA-Z0-9_-]+$ ]]
}

validate_type() {
    [[ "$1" == "metric" || "$1" == "log" || "$1" == "resource" ]]
}

validate_runtime_profile() {
    [[ "$1" == "standard" || "$1" == "docker" || "$1" == "custom" ]]
}

validate_absolute_path() {
    local value="$1"
    [[ "$value" == /* ]] && [[ "$value" != *$'\n'* ]] && [[ "$value" != *$'\r'* ]] && [[ "$value" != *\'* ]]
}

normalize_image_registry_prefix() {
    IMAGE_REGISTRY_PREFIX="$1" python -c '
import ipaddress
import os
import re
import sys

value = os.environ["IMAGE_REGISTRY_PREFIX"]
host_label = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
repository_component = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

def fail():
    sys.exit(1)

if not value or len(value) > 255 or value != value.strip() or any(ch.isspace() or ord(ch) < 32 for ch in value):
    fail()
if "://" in value or value.endswith("/"):
    fail()

host_port, *components = value.split("/")
if not components or not all(repository_component.fullmatch(component) for component in components):
    fail()

port = None
if host_port.startswith("["):
    match = re.fullmatch(r"\[([^]]+)](?::(\d{1,5}))?", host_port)
    if not match:
        fail()
    try:
        ipaddress.IPv6Address(match.group(1))
    except ValueError:
        fail()
    port = match.group(2)
else:
    if host_port.count(":") > 1:
        fail()
    host, separator, port = host_port.partition(":")
    if separator and not port:
        fail()
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        if not all(host_label.fullmatch(label) for label in host.split(".")):
            fail()

if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
    fail()
print(value, end="")
'
}

build_log_collect_filters() {
    NAMESPACE_PATTERNS="$1" POD_PATTERNS="$2" RUNTIME_PROFILE="$3" HOST_LOG_PATH="$4" DOCKER_CONTAINER_LOG_PATH="$5" python -c '
import hashlib
import json
import os
import re
import sys

WHITELIST = re.compile(r"^[a-z0-9.*?-]+$")
MAX_PER_DIMENSION = 50
MAX_INCLUDE_PATTERNS = 200


def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def validate_patterns(raw, field_name):
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        fail(f"Invalid {field_name}: must be a JSON array")
    if not isinstance(items, list):
        fail(f"Invalid {field_name}: must be a JSON array")
    if len(items) > MAX_PER_DIMENSION:
        fail(f"Invalid {field_name}: at most {MAX_PER_DIMENSION} items")

    normalized = []
    seen = set()
    for item in items:
        if not isinstance(item, str):
            fail(f"Invalid {field_name}: items must be strings")
        value = item.strip()
        if not value or value in seen:
            continue
        if "_" in value:
            fail(f"Invalid {field_name}: Kubernetes names do not contain underscore")
        if "**" in value:
            fail(f"Invalid {field_name}: ** is not allowed")
        if any(ch.isupper() for ch in value):
            fail(f"Invalid {field_name}: uppercase is not allowed")
        if not WHITELIST.fullmatch(value):
            fail(f"Invalid {field_name}: only lowercase letters, digits, -, ., *, ? are allowed")
        seen.add(value)
        normalized.append(value)
    return normalized


namespace_patterns = validate_patterns(os.environ["NAMESPACE_PATTERNS"], "namespace_patterns")
pod_patterns = validate_patterns(os.environ["POD_PATTERNS"], "pod_patterns")
if not namespace_patterns and not pod_patterns:
    include_patterns = []
else:
    namespace_globs = namespace_patterns or ["*"]
    pod_globs = pod_patterns or ["*"]
    include_patterns = [
        f"/var/log/pods/{namespace}_{pod}_*/**"
        for namespace in namespace_globs
        for pod in pod_globs
    ]
    if len(include_patterns) > MAX_INCLUDE_PATTERNS:
        fail(f"include_paths_glob_patterns exceeds {MAX_INCLUDE_PATTERNS} items")

if include_patterns:
    lines = ["        include_paths_glob_patterns:"]
    lines.extend(f"          - \"{pattern}\"" for pattern in include_patterns)
    include_yaml = "\n".join(lines) + "\n"
else:
    include_yaml = ""

canonical = json.dumps(
    {
        "runtime_profile": os.environ["RUNTIME_PROFILE"],
        "host_log_path": os.environ["HOST_LOG_PATH"],
        "docker_container_log_path": os.environ["DOCKER_CONTAINER_LOG_PATH"],
        "namespace_patterns": namespace_patterns,
        "pod_patterns": pod_patterns,
    },
    sort_keys=True,
    separators=(",", ":"),
)
config_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
print(json.dumps({"include_yaml": include_yaml, "config_hash": config_hash}))
'
}

require_field() {
    local field="$1" value="$2"
    if [ -z "$value" ]; then
        json_error "${CLUSTER_NAME:-unknown}" "Missing required field: $field"
        exit 1
    fi
}

require_field "cluster_name" "$CLUSTER_NAME"
validate_cluster_name "$CLUSTER_NAME" || { json_error "$CLUSTER_NAME" "Invalid cluster_name format (only alphanumeric, underscore and hyphen allowed)"; exit 1; }
require_field "type" "$TYPE"
validate_type "$TYPE" || { json_error "$CLUSTER_NAME" "Invalid type: must be 'metric', 'log' or 'resource'"; exit 1; }
require_field "nats_url" "$NATS_URL"
require_field "nats_username" "$NATS_USERNAME"
require_field "nats_password" "$NATS_PASSWORD"
require_field "nats_ca" "$NATS_CA"
validate_runtime_profile "$RUNTIME_PROFILE" || { json_error "$CLUSTER_NAME" "Invalid runtime_profile: must be 'standard', 'docker' or 'custom'"; exit 1; }
if ! IMAGE_REGISTRY_PREFIX=$(normalize_image_registry_prefix "$IMAGE_REGISTRY_PREFIX"); then
    json_error "$CLUSTER_NAME" "Invalid image_registry_prefix"
    exit 1
fi

if [ "$TYPE" == "log" ] && [ "$RUNTIME_PROFILE" == "custom" ]; then
    require_field "host_log_path" "$HOST_LOG_PATH"
    validate_absolute_path "$HOST_LOG_PATH" || { json_error "$CLUSTER_NAME" "Invalid host_log_path: must be an absolute path"; exit 1; }

    if [ -n "$DOCKER_CONTAINER_LOG_PATH" ]; then
        validate_absolute_path "$DOCKER_CONTAINER_LOG_PATH" || { json_error "$CLUSTER_NAME" "Invalid docker_container_log_path: must be an absolute path"; exit 1; }
    fi
fi

INCLUDE_PATHS_YAML=""
CONFIG_HASH="default"
if [ "$TYPE" == "log" ]; then
    if ! FILTERS_JSON=$(build_log_collect_filters "$NAMESPACE_PATTERNS" "$POD_PATTERNS" "$RUNTIME_PROFILE" "${HOST_LOG_PATH:-}" "${DOCKER_CONTAINER_LOG_PATH:-}" 2>&1); then
        json_error "$CLUSTER_NAME" "$FILTERS_JSON"
        exit 1
    fi
    INCLUDE_PATHS_YAML=$(echo "$FILTERS_JSON" | jq -r '.include_yaml')
    CONFIG_HASH=$(echo "$FILTERS_JSON" | jq -r '.config_hash')
fi

build_log_mount_block() {
    local runtime_profile="$1"
    local host_log_path="$2"
    local docker_container_log_path="$3"

    local normalized_host_log_path="${host_log_path:-/var/log}"
    local normalized_docker_container_log_path="${docker_container_log_path:-/var/lib/docker/containers}"

    case "$runtime_profile" in
        standard)
            cat <<'EOF'
            - name: var-log
              mountPath: /var/log
              readOnly: true
EOF
            ;;
        docker)
            cat <<'EOF'
            - name: var-log
              mountPath: /var/log
              readOnly: true
            - name: runtime-container-logs
              mountPath: /var/lib/docker/containers
              readOnly: true
EOF
            ;;
        custom)
            cat <<EOF
            - name: pod-log-dir
              mountPath: /var/log/pods
              readOnly: true
EOF
            if [ -n "$docker_container_log_path" ]; then
                cat <<EOF
            - name: docker-container-logs
              mountPath: ${normalized_docker_container_log_path}
              readOnly: true
EOF
            fi
            ;;
    esac
}

build_log_volume_block() {
    local runtime_profile="$1"
    local host_log_path="$2"
    local docker_container_log_path="$3"

    local normalized_host_log_path="${host_log_path:-/var/log}"
    local normalized_docker_container_log_path="${docker_container_log_path:-/var/lib/docker/containers}"

    case "$runtime_profile" in
        standard)
            cat <<'EOF'
        - name: var-log
          hostPath:
            path: /var/log
EOF
            ;;
        docker)
            cat <<'EOF'
        - name: var-log
          hostPath:
            path: /var/log
        - name: runtime-container-logs
          hostPath:
            path: /var/lib/docker/containers
EOF
            ;;
        custom)
            cat <<EOF
        - name: pod-log-dir
          hostPath:
            path: ${normalized_host_log_path}
EOF
            if [ -n "$docker_container_log_path" ]; then
                cat <<EOF
        - name: docker-container-logs
          hostPath:
            path: ${normalized_docker_container_log_path}
EOF
            fi
            ;;
    esac
}

replace_placeholder() {
    local content="$1"
    local placeholder="$2"
    local replacement="$3"

    CONTENT="$content" PLACEHOLDER="$placeholder" REPLACEMENT="$replacement" python -c 'import os
content = os.environ["CONTENT"]
placeholder = os.environ["PLACEHOLDER"]
replacement = os.environ["REPLACEMENT"]
print(content.replace(placeholder, replacement), end="")'
}

render_k8s_config() {
    local cluster_name="$1"
    local nats_url="$2"
    local nats_username="$3"
    local nats_password="$4"
    local nats_ca="$5"
    local type="$6"
    local runtime_profile="$7"
    local host_log_path="$8"
    local docker_container_log_path="$9"
    local include_paths_yaml="${10}"
    local config_hash="${11}"
    local image_registry_prefix="${12}"
    
    # 根据类型选择模板
    local template
    if [ "$type" == "log" ]; then
        template="$LOGS_TEMPLATE"
    elif [ "$type" == "resource" ]; then
        template="$RESOURCE_TEMPLATE"
    else
        template="$METRIC_TEMPLATE"
    fi

    template=$(replace_placeholder "$template" "__IMAGE_REGISTRY_PREFIX__" "$image_registry_prefix")

    if [ "$type" == "log" ]; then
        local log_mounts
        local log_volumes
        log_mounts=$(build_log_mount_block "$runtime_profile" "$host_log_path" "$docker_container_log_path")
        log_volumes=$(build_log_volume_block "$runtime_profile" "$host_log_path" "$docker_container_log_path")
        template=$(replace_placeholder "$template" "__LOG_VOLUME_MOUNTS__" "$log_mounts")
        template=$(replace_placeholder "$template" "__LOG_VOLUMES__" "$log_volumes")
        template=$(replace_placeholder "$template" "__INCLUDE_PATHS_GLOB_PATTERNS__" "$include_paths_yaml")
        template=$(replace_placeholder "$template" "__LOG_COLLECT_CONFIG_HASH__" "$config_hash")
    fi
    
    # Base64 编码
    local cluster_name_b64=$(echo -n "$cluster_name" | base64 | tr -d '\n')
    local nats_url_b64=$(echo -n "$nats_url" | base64 | tr -d '\n')
    local nats_username_b64=$(echo -n "$nats_username" | base64 | tr -d '\n')
    local nats_password_b64=$(echo -n "$nats_password" | base64 | tr -d '\n')
    local nats_ca_b64=$(echo -n "$nats_ca" | base64 | tr -d '\n')
    
    # 渲染 Secret
    local secret
    secret=$(echo "$SECRET_TEMPLATE" | \
        sed "s|\${CLUSTER_NAME_BASE64}|$cluster_name_b64|g" | \
        sed "s|\${NATS_URL_BASE64}|$nats_url_b64|g" | \
        sed "s|\${NATS_USERNAME_BASE64}|$nats_username_b64|g" | \
        sed "s|\${NATS_PASSWORD_BASE64}|$nats_password_b64|g" | \
        sed "s|\${NATS_CA_BASE64}|$nats_ca_b64|g")
    
    # 合并输出
    printf '%s\n---\n%s' "$template" "$secret"
}

# 执行渲染
K8S_CONFIG=$(render_k8s_config "$CLUSTER_NAME" "$NATS_URL" "$NATS_USERNAME" "$NATS_PASSWORD" "$NATS_CA" "$TYPE" "$RUNTIME_PROFILE" "$HOST_LOG_PATH" "$DOCKER_CONTAINER_LOG_PATH" "$INCLUDE_PATHS_YAML" "$CONFIG_HASH" "$IMAGE_REGISTRY_PREFIX")

# 返回成功响应，YAML 内容放在 yaml 字段中
json_success "$CLUSTER_NAME" "K8s configuration rendered successfully" "yaml" "$K8S_CONFIG"
exit 0

#!/bin/bash

# webhookd infra render script
# 接收 JSON: {"cluster_name": "xxx", "type": "metric|log", "nats_url": "nats://x.x.x.x:4222", "nats_username": "user", "nats_password": "pass", "nats_ca": "..."}
# 渲染出 K8s 配置 YAML

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBHOOKD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-logs-collector.yaml")
METRIC_TEMPLATE=$(cat "$WEBHOOKD_DIR/bk-lite-metric-collector.yaml")
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

# 验证必填字段
validate_cluster_name() {
    [[ "$1" =~ ^[a-zA-Z0-9_-]+$ ]]
}

validate_type() {
    [[ "$1" == "metric" || "$1" == "log" ]]
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
validate_type "$TYPE" || { json_error "$CLUSTER_NAME" "Invalid type: must be 'metric' or 'log'"; exit 1; }
require_field "nats_url" "$NATS_URL"
require_field "nats_username" "$NATS_USERNAME"
require_field "nats_password" "$NATS_PASSWORD"
require_field "nats_ca" "$NATS_CA"

# TODO: 渲染 K8s 配置 YAML
render_k8s_config() {
    local cluster_name="$1"
    local nats_url="$2"
    local nats_username="$3"
    local nats_password="$4"
    local nats_ca="$5"
    local type="$6"
    
    # 根据类型选择模板
    local template
    if [ "$type" == "log" ]; then
        template="$LOGS_TEMPLATE"
    else
        template="$METRIC_TEMPLATE"
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
K8S_CONFIG=$(render_k8s_config "$CLUSTER_NAME" "$NATS_URL" "$NATS_USERNAME" "$NATS_PASSWORD" "$NATS_CA" "$TYPE")

# 返回成功响应，YAML 内容放在 yaml 字段中
json_success "$CLUSTER_NAME" "K8s configuration rendered successfully" "yaml" "$K8S_CONFIG"
exit 0

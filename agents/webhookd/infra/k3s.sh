#!/bin/bash

# 独立 K3S 指标采集清单渲染器。
# 输入只接受 K3S 固定契约，不通过 type/distribution 等字段切换到 K8S。
set -euo pipefail

WEBHOOKD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JSON_DATA="${1:-$(cat)}"

json_error() {
    local id="$1"
    local message="$2"
    local field="${3:-}"
    jq -n \
        --arg id "$id" \
        --arg message "$message" \
        --arg field "$field" \
        '{status: "error", id: $id, message: $message}
         + (if $field == "" then {} else {field: $field} end)'
}

fail_field() {
    local id="$1"
    local field="$2"
    local message="$3"
    json_error "$id" "$message" "$field"
    exit 1
}

if [ -z "$JSON_DATA" ] || ! jq -e 'type == "object"' >/dev/null 2>&1 <<<"$JSON_DATA"; then
    json_error "" "Request body must be a JSON object"
    exit 1
fi

CLUSTER_NAME=$(jq -r '.cluster_name // empty' <<<"$JSON_DATA")

for field in type config_type distribution; do
    if jq -e --arg field "$field" 'has($field)' >/dev/null <<<"$JSON_DATA"; then
        fail_field "${CLUSTER_NAME:-unknown}" "$field" "Unsupported platform switch field: $field"
    fi
done

for field in cluster_name nats_url nats_username nats_password nats_ca; do
    value=$(jq -r --arg field "$field" '.[$field] // empty' <<<"$JSON_DATA")
    if [ -z "$value" ]; then
        fail_field "${CLUSTER_NAME:-unknown}" "$field" "Missing required field: $field"
    fi
done

if [[ ! "$CLUSTER_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    fail_field "$CLUSTER_NAME" "cluster_name" "Invalid cluster_name format"
fi

NATS_URL=$(jq -r '.nats_url' <<<"$JSON_DATA")
NATS_USERNAME=$(jq -r '.nats_username' <<<"$JSON_DATA")
NATS_PASSWORD=$(jq -r '.nats_password' <<<"$JSON_DATA")
NATS_CA=$(jq -r '.nats_ca' <<<"$JSON_DATA")

base64_value() {
    printf '%s' "$1" | base64 | tr -d '\n'
}

CLUSTER_NAME_BASE64=$(base64_value "$CLUSTER_NAME")
NATS_URL_BASE64=$(base64_value "$NATS_URL")
NATS_USERNAME_BASE64=$(base64_value "$NATS_USERNAME")
NATS_PASSWORD_BASE64=$(base64_value "$NATS_PASSWORD")
NATS_CA_BASE64=$(base64_value "$NATS_CA")

MANIFEST=$(cat "$WEBHOOKD_DIR/bk-lite-k3s-metric-collector.yaml")
SECRET=$(cat <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: k3s-monitor-config-secret
  namespace: bk-lite-k3s-collector
type: Opaque
data:
  CLUSTER_NAME: ${CLUSTER_NAME_BASE64}
  NATS_URL: ${NATS_URL_BASE64}
  NATS_USERNAME: ${NATS_USERNAME_BASE64}
  NATS_PASSWORD: ${NATS_PASSWORD_BASE64}
  ca.crt: ${NATS_CA_BASE64}
EOF
)

RENDERED=$(printf '%s\n---\n%s' "$MANIFEST" "$SECRET")
jq -n \
    --arg id "$CLUSTER_NAME" \
    --arg yaml "$RENDERED" \
    '{
        status: "success",
        id: $id,
        message: "K3S configuration rendered successfully",
        yaml: $yaml
    }'

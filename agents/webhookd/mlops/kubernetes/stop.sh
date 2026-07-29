#!/bin/bash

# webhookd mlops stop script (Kubernetes)
# 接收 JSON: {"id": "train-001", "remove": false, "namespace": "mlops"}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh" || {
    echo '{"status":"error","code":"COMMON_SH_LOAD_FAILED","message":"Failed to load common.sh"}'
    exit 1
}

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "INVALID_JSON" "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 检查 jq 是否可用
if ! command -v jq >/dev/null 2>&1; then
    json_error "JQ_NOT_FOUND" "" "jq command not found"
    exit 1
fi

# 检查 kubectl 是否可用
if ! command -v kubectl >/dev/null 2>&1; then
    json_error "KUBECTL_NOT_FOUND" "" "kubectl command not found"
    exit 1
fi

# 提取参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null) || {
    json_error "JSON_PARSE_FAILED" "" "Failed to parse JSON data"
    exit 1
}
REMOVE=$(echo "$JSON_DATA" | jq -r 'if has("remove") then .remove else true end')
NAMESPACE=$(echo "$JSON_DATA" | jq -r '.namespace // empty')

if [ -z "$ID" ]; then
    json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id"
    exit 1
fi

# K8s 资源名称（DNS-1123 合规）
K8S_NAME=$(sanitize_k8s_name "$ID")

# 使用默认命名空间（如果未指定）
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="$KUBERNETES_NAMESPACE"
fi

# 独立检查全部资源。历史失败可能留下孤儿 Service，不能只凭
# Job/Deployment 不存在就宣称该运行时 ID 已可复用。
set +e
JOB_EXISTS=$(kubectl get job "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
JOB_GET_STATUS=$?
DEPLOYMENT_EXISTS=$(kubectl get deployment "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
DEPLOYMENT_GET_STATUS=$?
SERVICE_NAME="${K8S_NAME}-svc"
SERVICE_EXISTS=$(kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
SERVICE_GET_STATUS=$?
set -e

if [ $JOB_GET_STATUS -ne 0 ] || [ $DEPLOYMENT_GET_STATUS -ne 0 ] || [ $SERVICE_GET_STATUS -ne 0 ]; then
    json_error "RESOURCE_QUERY_FAILED" "$ID" "Failed to query Kubernetes resources before stopping"
    exit 1
fi

DELETION_STARTED="false"

if [ -n "$JOB_EXISTS" ]; then
    # 这是一个训练 Job
    # Kubernetes Job 无法"停止"，只能删除
    if [ "$REMOVE" = "true" ]; then
        # 删除 Job（会级联删除关联的 Pod），使用 --wait=false 立即返回
        set +e
        DELETE_OUTPUT=$(kubectl delete job "$K8S_NAME" -n "$NAMESPACE" --wait=false 2>&1)
        DELETE_STATUS=$?
        set -e
        
        if [ $DELETE_STATUS -ne 0 ]; then
            json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete job" "$DELETE_OUTPUT"
            exit 1
        fi
        DELETION_STARTED="true"
        
        # 删除关联的 Secret
        SECRET_NAME=$(generate_secret_name "$K8S_NAME")
        delete_secret "$NAMESPACE" "$SECRET_NAME"
        
    else
        # Job 无法停止，只能删除
        json_error "JOB_CANNOT_STOP" "$ID" "Kubernetes Jobs cannot be stopped, only deleted. Use remove=true to delete."
        exit 1
    fi
fi

if [ -n "$DEPLOYMENT_EXISTS" ]; then
    # 这是一个推理 Deployment
    # 注意：为了与 Docker --rm 行为一致，stop 操作会删除 Deployment
    # 这样可以保证同一个 serving ID 可以"停止 → 重新部署"
    
    # 删除 Deployment（使用 --wait=false 立即返回，不等待 Pod 终止）
    set +e
    DELETE_OUTPUT=$(kubectl delete deployment "$K8S_NAME" -n "$NAMESPACE" --wait=false 2>&1)
    DELETE_STATUS=$?
    set -e
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "DEPLOYMENT_DELETE_FAILED" "$ID" "Failed to delete deployment" "$DELETE_OUTPUT"
        exit 1
    fi
    DELETION_STARTED="true"
fi

# Service 可能独立残留，必须单独删除。
if [ -n "$SERVICE_EXISTS" ]; then
    set +e
    SVC_DELETE_OUTPUT=$(kubectl delete service "$SERVICE_NAME" -n "$NAMESPACE" --wait=false 2>&1)
    SVC_DELETE_STATUS=$?
    set -e

    if [ $SVC_DELETE_STATUS -ne 0 ]; then
        json_error "SERVICE_DELETE_FAILED" "$ID" "Failed to delete Service" "$SVC_DELETE_OUTPUT"
        exit 1
    fi
    DELETION_STARTED="true"
fi

if [ "$DELETION_STARTED" = "true" ]; then
    echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"terminating\",\"detail\":\"Kubernetes resource deletion initiated\"}"
    exit 0
fi

# 资源不存在（幂等终态）
json_success "$ID" "Resource does not exist (already stopped or removed)" "state" "removed"
exit 0

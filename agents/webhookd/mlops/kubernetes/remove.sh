#!/bin/bash

# webhookd mlops remove script (Kubernetes)
# 接收 JSON: {"id": "serving-001", "namespace": "mlops"}

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

# 提取 id 和 namespace
ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null) || {
    json_error "JSON_PARSE_FAILED" "" "Failed to parse JSON data"
    exit 1
}
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

# 检查资源类型
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
    json_error "RESOURCE_QUERY_FAILED" "$ID" "Failed to query Kubernetes resources before removal"
    exit 1
fi

DELETED_RESOURCES=""

if [ -n "$JOB_EXISTS" ]; then
    # 删除 Job
    set +e
    DELETE_OUTPUT=$(kubectl delete job "$K8S_NAME" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    set -e
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete job" "$DELETE_OUTPUT"
        exit 1
    fi
    
    DELETED_RESOURCES="Job"
    
    # 删除关联的 Secret
    SECRET_NAME=$(generate_secret_name "$K8S_NAME")
    delete_secret "$NAMESPACE" "$SECRET_NAME"
fi

if [ -n "$DEPLOYMENT_EXISTS" ]; then
    # 删除 Deployment
    set +e
    DELETE_OUTPUT=$(kubectl delete deployment "$K8S_NAME" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    set -e
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "DEPLOYMENT_DELETE_FAILED" "$ID" "Failed to delete deployment" "$DELETE_OUTPUT"
        exit 1
    fi
    
    if [ -n "$DELETED_RESOURCES" ]; then
        DELETED_RESOURCES="$DELETED_RESOURCES, Deployment"
    else
        DELETED_RESOURCES="Deployment"
    fi
fi

# Service 可能在 Deployment 创建失败或已被单独删除后独立残留，必须单独处理。
if [ -n "$SERVICE_EXISTS" ]; then
    set +e
    DELETE_OUTPUT=$(kubectl delete service "$SERVICE_NAME" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    set -e

    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "SERVICE_DELETE_FAILED" "$ID" "Failed to delete service" "$DELETE_OUTPUT"
        exit 1
    fi

    if [ -n "$DELETED_RESOURCES" ]; then
        DELETED_RESOURCES="$DELETED_RESOURCES, Service"
    else
        DELETED_RESOURCES="Service"
    fi
fi

# 删除命令成功后再次查询，只有目标资源全部消失才允许复用同一运行时 ID。
set +e
REMAINING_JOB=$(kubectl get job "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
JOB_VERIFY_STATUS=$?
REMAINING_DEPLOYMENT=$(kubectl get deployment "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
DEPLOYMENT_VERIFY_STATUS=$?
REMAINING_SERVICE=$(kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
SERVICE_VERIFY_STATUS=$?
set -e

if [ $JOB_VERIFY_STATUS -ne 0 ] || [ $DEPLOYMENT_VERIFY_STATUS -ne 0 ] || [ $SERVICE_VERIFY_STATUS -ne 0 ]; then
    json_error "RESOURCE_VERIFY_FAILED" "$ID" "Failed to verify Kubernetes resources after removal"
    exit 1
fi

if [ -n "$REMAINING_JOB" ] || [ -n "$REMAINING_DEPLOYMENT" ] || [ -n "$REMAINING_SERVICE" ]; then
    json_error "RESOURCE_DELETE_INCOMPLETE" "$ID" "Kubernetes resources still exist after removal"
    exit 1
fi

if [ -z "$DELETED_RESOURCES" ]; then
    # 没有找到任何资源（幂等设计：不存在时返回成功）
    json_success "$ID" "No resources found (already removed)"
    exit 0
fi

# 成功删除
json_success "$ID" "Resources removed successfully: $DELETED_RESOURCES"
exit 0

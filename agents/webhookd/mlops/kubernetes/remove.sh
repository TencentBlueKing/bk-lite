#!/bin/bash

# webhookd mlops remove script (Kubernetes)
# 接收 JSON: {"id": "serving-001", "namespace": "mlops"}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "INVALID_JSON" "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 检查 kubectl 是否可用
if ! command -v kubectl >/dev/null 2>&1; then
    echo '{"status":"error","code":"KUBECTL_NOT_FOUND","message":"kubectl command not found"}' >&2
    exit 1
fi

# 提取 id 和 namespace
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
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
DEPLOYMENT_EXISTS=$(kubectl get deployment "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
set -e

DELETED_RESOURCES=""

if [ -n "$JOB_EXISTS" ]; then
    # 删除 Job
    DELETE_OUTPUT=$(kubectl delete job "$K8S_NAME" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    
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
    DELETE_OUTPUT=$(kubectl delete deployment "$K8S_NAME" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "DEPLOYMENT_DELETE_FAILED" "$ID" "Failed to delete deployment" "$DELETE_OUTPUT"
        exit 1
    fi
    
    if [ -n "$DELETED_RESOURCES" ]; then
        DELETED_RESOURCES="$DELETED_RESOURCES, Deployment"
    else
        DELETED_RESOURCES="Deployment"
    fi
    
    # 删除 Service
    SERVICE_NAME="${K8S_NAME}-svc"
    set +e
    SERVICE_EXISTS=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
    set -e
    
    if [ -n "$SERVICE_EXISTS" ]; then
        kubectl delete svc "$SERVICE_NAME" -n "$NAMESPACE" >/dev/null 2>&1 || true
        DELETED_RESOURCES="$DELETED_RESOURCES, Service"
    fi
fi

if [ -z "$DELETED_RESOURCES" ]; then
    # 没有找到任何资源
    json_error "RESOURCE_NOT_FOUND" "$ID" "No resources found to delete"
    exit 1
fi

# 成功删除
json_success "$ID" "Resources removed successfully: $DELETED_RESOURCES"
exit 0

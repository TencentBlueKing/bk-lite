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

# 检查资源类型
set +e
JOB_EXISTS=$(kubectl get job "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
DEPLOYMENT_EXISTS=$(kubectl get deployment "$K8S_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
set -e

if [ -n "$JOB_EXISTS" ]; then
    # 这是一个训练 Job
    # Kubernetes Job 无法"停止"，只能删除
    if [ "$REMOVE" = "true" ]; then
        # 删除 Job（会级联删除关联的 Pod），使用 --wait=false 立即返回
        DELETE_OUTPUT=$(kubectl delete job "$K8S_NAME" -n "$NAMESPACE" --wait=false 2>&1)
        DELETE_STATUS=$?
        
        if [ $DELETE_STATUS -ne 0 ]; then
            json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete job" "$DELETE_OUTPUT"
            exit 1
        fi
        
        # 删除关联的 Secret
        SECRET_NAME=$(generate_secret_name "$K8S_NAME")
        delete_secret "$NAMESPACE" "$SECRET_NAME"
        
        # 返回 terminating 状态，前端通过 status 接口轮询最终状态
        echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"terminating\",\"detail\":\"Job deletion initiated\"}"
        exit 0
    else
        # Job 无法停止，只能删除
        json_error "JOB_CANNOT_STOP" "$ID" "Kubernetes Jobs cannot be stopped, only deleted. Use remove=true to delete."
        exit 1
    fi
elif [ -n "$DEPLOYMENT_EXISTS" ]; then
    # 这是一个推理 Deployment
    # 注意：为了与 Docker --rm 行为一致，stop 操作会删除 Deployment
    # 这样可以保证同一个 serving ID 可以"停止 → 重新部署"
    
    SERVICE_NAME="${K8S_NAME}-svc"
    
    # 删除 Deployment（使用 --wait=false 立即返回，不等待 Pod 终止）
    DELETE_OUTPUT=$(kubectl delete deployment "$K8S_NAME" -n "$NAMESPACE" --wait=false 2>&1)
    DELETE_STATUS=$?
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "DEPLOYMENT_DELETE_FAILED" "$ID" "Failed to delete deployment" "$DELETE_OUTPUT"
        exit 1
    fi
    
    # 删除 Service（使用 --wait=false 立即返回）
    set +e
    SVC_EXISTS=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
    if [ -n "$SVC_EXISTS" ]; then
        SVC_DELETE_OUTPUT=$(kubectl delete svc "$SERVICE_NAME" -n "$NAMESPACE" --wait=false 2>&1)
        SVC_DELETE_STATUS=$?
        if [ $SVC_DELETE_STATUS -ne 0 ]; then
            # Service 删除失败，记录但不阻塞（Deployment 已删除）
            json_error "SERVICE_DELETE_FAILED" "$ID" "Deployment deleted but Service deletion failed" "$SVC_DELETE_OUTPUT"
            exit 1
        fi
    fi
    set -e
    
    # 返回 terminating 状态，前端通过 status 接口轮询最终状态
    echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"terminating\",\"detail\":\"Deployment and Service deletion initiated\"}"
    exit 0
else
    # 资源不存在
    json_error "RESOURCE_NOT_FOUND" "$ID" "Resource not found"
    exit 1
fi

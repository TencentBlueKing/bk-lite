#!/bin/bash

# webhookd mlops stop script (Kubernetes)
# 接收 JSON: {"id": "train-001", "remove": false, "namespace": "mlops"}

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

# 提取参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
REMOVE=$(echo "$JSON_DATA" | jq -r 'if has("remove") then .remove else true end')
NAMESPACE=$(echo "$JSON_DATA" | jq -r '.namespace // empty')

if [ -z "$ID" ]; then
    json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id"
    exit 1
fi

# 使用默认命名空间（如果未指定）
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="$KUBERNETES_NAMESPACE"
fi

# 检查资源类型
set +e
JOB_EXISTS=$(kubectl get job "$ID" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
DEPLOYMENT_EXISTS=$(kubectl get deployment "$ID" -n "$NAMESPACE" --ignore-not-found 2>/dev/null)
set -e

if [ -n "$JOB_EXISTS" ]; then
    # 这是一个训练 Job
    # Kubernetes Job 无法"停止"，只能删除
    if [ "$REMOVE" = "true" ]; then
        # 删除 Job（会级联删除关联的 Pod）
        DELETE_OUTPUT=$(kubectl delete job "$ID" -n "$NAMESPACE" 2>&1)
        DELETE_STATUS=$?
        
        if [ $DELETE_STATUS -ne 0 ]; then
            json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete job" "$DELETE_OUTPUT"
            exit 1
        fi
        
        # 删除关联的 Secret
        SECRET_NAME=$(generate_secret_name "$ID")
        delete_secret "$NAMESPACE" "$SECRET_NAME"
        
        json_success "$ID" "Job deleted successfully"
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
    
    SERVICE_NAME="${ID}-svc"
    
    # 删除 Deployment（模拟 docker stop + --rm）
    DELETE_OUTPUT=$(kubectl delete deployment "$ID" -n "$NAMESPACE" 2>&1)
    DELETE_STATUS=$?
    
    if [ $DELETE_STATUS -ne 0 ]; then
        json_error "DEPLOYMENT_DELETE_FAILED" "$ID" "Failed to delete deployment" "$DELETE_OUTPUT"
        exit 1
    fi
    
    # 删除 Service（如果存在）
    set +e
    kubectl delete svc "$SERVICE_NAME" -n "$NAMESPACE" >/dev/null 2>&1
    set -e
    
    if [ "$REMOVE" = "true" ]; then
        json_success "$ID" "Deployment and Service deleted successfully"
    else
        json_success "$ID" "Deployment stopped and deleted (to match Docker --rm behavior)"
    fi
    exit 0
else
    # 资源不存在
    json_error "RESOURCE_NOT_FOUND" "$ID" "Resource not found"
    exit 1
fi

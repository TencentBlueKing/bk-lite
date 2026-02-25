#!/bin/bash

# webhookd mlops logs script (Kubernetes)
# 接收 JSON: {"id": "train-001", "lines": 100, "namespace": "mlops"}

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
LINES=$(echo "$JSON_DATA" | jq -r '.lines // "100"')
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

# 尝试查找对应的 Pod
set +e

# 首先尝试查找 Job 对应的 Pod（训练任务）
JOB_POD=$(kubectl get pods -n "$NAMESPACE" -l "job-name=${K8S_NAME}" --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null)

if [ -n "$JOB_POD" ]; then
    # 找到了 Job 的 Pod
    POD_NAME="$JOB_POD"
else
    # 尝试查找 Deployment 对应的 Pod（推理服务）
    DEPLOYMENT_POD=$(kubectl get pods -n "$NAMESPACE" -l "service-id=${ID}" --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null)
    
    if [ -n "$DEPLOYMENT_POD" ]; then
        POD_NAME="$DEPLOYMENT_POD"
    else
        # 都没找到
        json_error "POD_NOT_FOUND" "$ID" "No pods found for resource: $ID"
        exit 1
    fi
fi

set -e

# 获取日志
LOGS=$(kubectl logs "$POD_NAME" -n "$NAMESPACE" --tail="$LINES" 2>&1)
KUBECTL_STATUS=$?

if [ $KUBECTL_STATUS -eq 0 ]; then
    # 转义日志内容为 JSON
    LOGS_ESCAPED=$(echo "$LOGS" | jq -Rs .)
    echo "{\"status\":\"success\",\"id\":\"$ID\",\"pod\":\"$POD_NAME\",\"logs\":$LOGS_ESCAPED}"
    exit 0
else
    json_error "LOGS_RETRIEVAL_FAILED" "$ID" "Failed to retrieve logs from pod: $POD_NAME" "$LOGS"
    exit 1
fi

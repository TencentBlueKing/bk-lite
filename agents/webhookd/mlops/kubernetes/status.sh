#!/bin/bash

# webhookd mlops status script (Kubernetes)
# 接收 JSON: {"id": "train-001", "namespace": "mlops"} 或 {"ids": ["train-001", "train-002"], "namespace": "mlops"}

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

# 提取参数（单个或多个）
set +e
SINGLE_ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null)
HAS_IDS=$(echo "$JSON_DATA" | jq -r 'if .ids then "true" else "false" end' 2>/dev/null)
NAMESPACE=$(echo "$JSON_DATA" | jq -r '.namespace // empty' 2>/dev/null)
set -e

# 使用默认命名空间（如果未指定）
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="$KUBERNETES_NAMESPACE"
fi

# 构建资源 ID 数组
if [ -n "$SINGLE_ID" ] && [ "$SINGLE_ID" != "null" ]; then
    # 单个查询（向后兼容）
    IDS=("$SINGLE_ID")
elif [ "$HAS_IDS" = "true" ]; then
    # 批量查询
    set +e
    mapfile -t IDS < <(echo "$JSON_DATA" | jq -r '.ids[]' 2>/dev/null)
    set -e
    
    # 检查是否成功读取到数据
    if [ ${#IDS[@]} -eq 0 ]; then
        json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id or ids"
        exit 1
    fi
else
    json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id or ids"
    exit 1
fi

# 查询资源状态的辅助函数
query_resource_status() {
    local resource_id="$1"
    local namespace="$2"
    
    # 尝试查询 Job（训练任务）
    set +e
    JOB_EXISTS=$(kubectl get job "$resource_id" -n "$namespace" --ignore-not-found 2>/dev/null)
    set -e
    
    if [ -n "$JOB_EXISTS" ]; then
        # 这是一个训练 Job
        set +e
        JOB_STATUS=$(kubectl get job "$resource_id" -n "$namespace" -o json 2>/dev/null)
        set -e
        
        if [ -z "$JOB_STATUS" ]; then
            echo "{\"status\":\"success\",\"id\":\"$resource_id\",\"state\":\"not_found\",\"port\":\"\",\"detail\":\"Job does not exist\"}"
            return
        fi
        
        # 解析 Job 状态
        ACTIVE=$(echo "$JOB_STATUS" | jq -r '.status.active // 0')
        SUCCEEDED=$(echo "$JOB_STATUS" | jq -r '.status.succeeded // 0')
        FAILED=$(echo "$JOB_STATUS" | jq -r '.status.failed // 0')
        START_TIME=$(echo "$JOB_STATUS" | jq -r '.status.startTime // ""')
        COMPLETION_TIME=$(echo "$JOB_STATUS" | jq -r '.status.completionTime // ""')
        
        # 判断状态
        if [ "$SUCCEEDED" -gt 0 ]; then
            STATUS="completed"
            DETAIL="Job completed successfully"
            
            # 计算完成时间
            if [ -n "$COMPLETION_TIME" ] && [ "$COMPLETION_TIME" != "null" ]; then
                COMPLETION_TS=$(date -d "$COMPLETION_TIME" +%s 2>/dev/null || echo "")
                if [ -n "$COMPLETION_TS" ]; then
                    CURRENT_TS=$(date +%s)
                    COMPLETED_SECONDS=$((CURRENT_TS - COMPLETION_TS))
                    
                    if [ $COMPLETED_SECONDS -ge 86400 ]; then
                        DAYS=$((COMPLETED_SECONDS / 86400))
                        DETAIL="$DETAIL, completed ${DAYS} days ago"
                    elif [ $COMPLETED_SECONDS -ge 3600 ]; then
                        HOURS=$((COMPLETED_SECONDS / 3600))
                        DETAIL="$DETAIL, completed ${HOURS} hours ago"
                    elif [ $COMPLETED_SECONDS -ge 60 ]; then
                        MINUTES=$((COMPLETED_SECONDS / 60))
                        DETAIL="$DETAIL, completed ${MINUTES} minutes ago"
                    else
                        DETAIL="$DETAIL, completed ${COMPLETED_SECONDS} seconds ago"
                    fi
                fi
            fi
        elif [ "$FAILED" -gt 0 ]; then
            STATUS="failed"
            # 获取失败原因（从 Pod 中获取）
            POD_NAME=$(kubectl get pods -n "$namespace" -l "job-name=${resource_id}" --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || echo "")
            if [ -n "$POD_NAME" ]; then
                POD_REASON=$(kubectl get pod "$POD_NAME" -n "$namespace" -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || echo "Unknown")
                DETAIL="Job failed (reason: $POD_REASON)"
            else
                DETAIL="Job failed"
            fi
        elif [ "$ACTIVE" -gt 0 ]; then
            STATUS="running"
            # 计算运行时长
            if [ -n "$START_TIME" ] && [ "$START_TIME" != "null" ]; then
                START_TS=$(date -d "$START_TIME" +%s 2>/dev/null || echo "")
                if [ -n "$START_TS" ]; then
                    CURRENT_TS=$(date +%s)
                    RUNNING_SECONDS=$((CURRENT_TS - START_TS))
                    
                    if [ $RUNNING_SECONDS -ge 86400 ]; then
                        DAYS=$((RUNNING_SECONDS / 86400))
                        DETAIL="Job running for ${DAYS} days"
                    elif [ $RUNNING_SECONDS -ge 3600 ]; then
                        HOURS=$((RUNNING_SECONDS / 3600))
                        DETAIL="Job running for ${HOURS} hours"
                    elif [ $RUNNING_SECONDS -ge 60 ]; then
                        MINUTES=$((RUNNING_SECONDS / 60))
                        DETAIL="Job running for ${MINUTES} minutes"
                    else
                        DETAIL="Job running for ${RUNNING_SECONDS} seconds"
                    fi
                else
                    DETAIL="Job running"
                fi
            else
                DETAIL="Job running"
            fi
        else
            STATUS="pending"
            DETAIL="Job pending (waiting for pod creation)"
        fi
        
        echo "{\"status\":\"success\",\"id\":\"$resource_id\",\"state\":\"$STATUS\",\"port\":\"\",\"detail\":\"$DETAIL\"}"
        return
    fi
    
    # 尝试查询 Deployment（推理服务）
    set +e
    DEPLOYMENT_EXISTS=$(kubectl get deployment "$resource_id" -n "$namespace" --ignore-not-found 2>/dev/null)
    set -e
    
    if [ -n "$DEPLOYMENT_EXISTS" ]; then
        # 这是一个推理 Deployment
        set +e
        DEPLOYMENT_STATUS=$(kubectl get deployment "$resource_id" -n "$namespace" -o json 2>/dev/null)
        set -e
        
        if [ -z "$DEPLOYMENT_STATUS" ]; then
            echo "{\"status\":\"success\",\"id\":\"$resource_id\",\"state\":\"not_found\",\"port\":\"\",\"detail\":\"Deployment does not exist\"}"
            return
        fi
        
        # 解析 Deployment 状态
        DESIRED=$(echo "$DEPLOYMENT_STATUS" | jq -r '.status.replicas // 0')
        READY=$(echo "$DEPLOYMENT_STATUS" | jq -r '.status.readyReplicas // 0')
        AVAILABLE=$(echo "$DEPLOYMENT_STATUS" | jq -r '.status.availableReplicas // 0')
        
        # 获取 Service 端口
        SERVICE_NAME="${resource_id}-svc"
        set +e
        SERVICE_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$namespace" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
        if [ -z "$SERVICE_PORT" ]; then
            SERVICE_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$namespace" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "")
        fi
        set -e
        
        # 判断状态
        if [ "$READY" -eq "$DESIRED" ] && [ "$DESIRED" -gt 0 ]; then
            STATUS="running"
            DETAIL="Deployment ready with ${READY}/${DESIRED} replicas"
        elif [ "$READY" -gt 0 ]; then
            STATUS="running"
            DETAIL="Deployment partially ready (${READY}/${DESIRED} replicas)"
        elif [ "$DESIRED" -gt 0 ]; then
            STATUS="pending"
            DETAIL="Deployment starting (0/${DESIRED} replicas ready)"
        else
            STATUS="stopped"
            DETAIL="Deployment scaled to 0"
        fi
        
        echo "{\"status\":\"success\",\"id\":\"$resource_id\",\"state\":\"$STATUS\",\"port\":\"$SERVICE_PORT\",\"detail\":\"$DETAIL\"}"
        return
    fi
    
    # 资源不存在
    echo "{\"status\":\"success\",\"id\":\"$resource_id\",\"state\":\"not_found\",\"port\":\"\",\"detail\":\"Resource does not exist\"}"
}

# 构建结果数组
RESULTS="["
FIRST=true

for resource_id in "${IDS[@]}"; do
    RESULT=$(query_resource_status "$resource_id" "$NAMESPACE")
    
    if [ "$FIRST" = false ]; then
        RESULTS="$RESULTS,"
    fi
    RESULTS="$RESULTS$RESULT"
    FIRST=false
done

RESULTS="$RESULTS]"

# 返回结果（统一为数组格式）
echo "{\"status\":\"success\",\"results\":$RESULTS}"
exit 0

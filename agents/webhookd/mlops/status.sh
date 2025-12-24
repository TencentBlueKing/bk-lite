#!/bin/bash

# webhookd mlops status script
# 接收 JSON: {"id": "train-001"} 或 {"ids": ["train-001", "train-002"]}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 提取参数（单个或多个）
SINGLE_ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
BATCH_IDS=$(echo "$JSON_DATA" | jq -r '.ids // empty')

# 构建容器 ID 数组
if [ -n "$SINGLE_ID" ] && [ "$SINGLE_ID" != "null" ]; then
    # 单个查询（向后兼容）
    IDS=("$SINGLE_ID")
elif [ "$BATCH_IDS" != "null" ] && [ "$BATCH_IDS" != "" ]; then
    # 批量查询
    mapfile -t IDS < <(echo "$JSON_DATA" | jq -r '.ids[]')
else
    json_error "unknown" "Missing required field: id or ids"
    exit 1
fi

# ============ 关键优化：一次性 inspect 所有指定容器 ============
# 使用 docker inspect 批量查询（只查询指定的容器，不查询所有）
INSPECT_OUTPUT=$(docker inspect "${IDS[@]}" 2>&1)
INSPECT_STATUS=$?

# 构建结果数组
RESULTS="["
FIRST=true

if [ $INSPECT_STATUS -eq 0 ]; then
    # inspect 成功，解析每个容器的状态
    for container_id in "${IDS[@]}"; do
        # 从 inspect 输出中提取该容器的信息
        CONTAINER_DATA=$(echo "$INSPECT_OUTPUT" | jq -r ".[] | select(.Name == \"/${container_id}\" or .Name == \"${container_id}\")")
        
        if [ -z "$CONTAINER_DATA" ]; then
            # 容器不存在
            if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
            RESULTS="$RESULTS{\"status\":\"error\",\"id\":\"$container_id\",\"message\":\"Container not found\"}"
            FIRST=false
            continue
        fi
        
        # 提取状态信息
        STATE_STATUS=$(echo "$CONTAINER_DATA" | jq -r '.State.Status // "unknown"')
        STATE_EXIT_CODE=$(echo "$CONTAINER_DATA" | jq -r '.State.ExitCode // 0')
        STATE_STARTED_AT=$(echo "$CONTAINER_DATA" | jq -r '.State.StartedAt // ""')
        
        # 从环境变量中提取端口号
        PORT=$(echo "$CONTAINER_DATA" | jq -r '.Config.Env[]? | select(startswith("BENTOML_PORT=")) | split("=")[1] // ""')
        
        # 判断状态
        case "$STATE_STATUS" in
            "running")
                STATUS="running"
                ;;
            "exited")
                if [ "$STATE_EXIT_CODE" = "0" ]; then
                    STATUS="completed"
                else
                    STATUS="failed"
                fi
                ;;
            *)
                STATUS="unknown"
                ;;
        esac
        
        # 构造 detail 信息
        if [ "$STATE_STATUS" = "running" ]; then
            DETAIL="Up"
        else
            DETAIL="Exited ($STATE_EXIT_CODE)"
        fi
        
        # 添加到结果
        if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
        RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"$STATUS\",\"port\":\"$PORT\",\"detail\":\"$DETAIL\"}"
        FIRST=false
    done
else
    # inspect 失败，可能是部分容器不存在
    # 尝试逐个查询（兼容处理）
    for container_id in "${IDS[@]}"; do
        CONTAINER_INFO=$(docker ps -a --filter "name=^${container_id}$" --format '{{.Status}}' 2>/dev/null)
        
        if [ -z "$CONTAINER_INFO" ]; then
            # 容器不存在
            if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
            RESULTS="$RESULTS{\"status\":\"error\",\"id\":\"$container_id\",\"message\":\"Container not found\"}"
            FIRST=false
            continue
        fi
        
        # 判断状态
        if echo "$CONTAINER_INFO" | grep -q "Up"; then
            STATUS="running"
        elif echo "$CONTAINER_INFO" | grep -q "Exited (0)"; then
            STATUS="completed"
        elif echo "$CONTAINER_INFO" | grep -q "Exited"; then
            STATUS="failed"
        else
            STATUS="unknown"
        fi
        
        # 从环境变量提取端口（兼容处理分支）
        PORT=$(docker inspect "$container_id" -f '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep "BENTOML_PORT=" | cut -d= -f2 || echo "")
        
        # 添加到结果
        if [ "$FIRST" = false ]; then RESULTS="$RESULTS,"; fi
        RESULTS="$RESULTS{\"status\":\"success\",\"id\":\"$container_id\",\"state\":\"$STATUS\",\"port\":\"$PORT\",\"detail\":\"$CONTAINER_INFO\"}"
        FIRST=false
    done
fi

RESULTS="$RESULTS]"

# 返回结果（统一为数组格式）
echo "{\"status\":\"success\",\"results\":$RESULTS}"
exit 0

#!/bin/bash

# webhookd mlops remove script
# 接收 JSON: {"id": "serving-001"}

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

# 提取 id
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')

if [ -z "$ID" ]; then
    json_error "MISSING_REQUIRED_FIELD" "unknown" "Missing required field: id"
    exit 1
fi

# 容器名称
CONTAINER_NAME="${ID}"

# 检查容器是否存在
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    json_error "CONTAINER_NOT_FOUND" "$ID" "Container not found"
    exit 1
fi

# 如果容器还在运行，先停止
if docker ps -q -f name="^${CONTAINER_NAME}$" | grep -q .; then
    STOP_OUTPUT=$(docker stop --time=5 "$CONTAINER_NAME" 2>&1)
    STOP_STATUS=$?
    
    if [ $STOP_STATUS -ne 0 ]; then
        json_error "CONTAINER_STOP_FAILED" "$ID" "Failed to stop container" "$STOP_OUTPUT"
        exit 1
    fi
fi

# 删除容器
RM_OUTPUT=$(docker rm "$CONTAINER_NAME" 2>&1)
RM_STATUS=$?

if [ $RM_STATUS -eq 0 ]; then
    json_success "$ID" "Container removed successfully"
    exit 0
else
    json_error "CONTAINER_REMOVE_FAILED" "$ID" "Failed to remove container" "$RM_OUTPUT"
    exit 1
fi

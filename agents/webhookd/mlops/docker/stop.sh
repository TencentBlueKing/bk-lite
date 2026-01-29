#!/bin/bash

# webhookd mlops stop script
# 接收 JSON: {"id": "train-001", "remove": false}

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

# 提取参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
REMOVE=$(echo "$JSON_DATA" | jq -r 'if has("remove") then .remove else true end')

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

# 停止容器（5秒超时，避免 webhookd 总超时）
STOP_OUTPUT=$(docker stop --time=5 "$CONTAINER_NAME" 2>&1)
DOCKER_STATUS=$?

if [ $DOCKER_STATUS -ne 0 ]; then
    json_error "CONTAINER_STOP_FAILED" "$ID" "Failed to stop container" "$STOP_OUTPUT"
    exit 1
fi

# 根据 remove 参数决定是否删除容器
if [ "$REMOVE" = "true" ]; then
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
    json_success "$ID" "Container stopped and removed"
else
    json_success "$ID" "Container stopped (use remove.sh to delete)"
fi

exit 0

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

# 检查容器是否存在（幂等设计：不存在时返回成功）
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    json_success "$ID" "Container does not exist (already stopped or removed)" "state" "removed"
    exit 0
fi

# 停止容器（5秒超时，避免 webhookd 总超时）
set +e
STOP_OUTPUT=$(docker stop --time=5 "$CONTAINER_NAME" 2>&1)
DOCKER_STATUS=$?
set -e

if [ $DOCKER_STATUS -ne 0 ]; then
    json_error "CONTAINER_STOP_FAILED" "$ID" "Failed to stop container" "$STOP_OUTPUT"
    exit 1
fi

# 根据 remove 参数决定是否删除容器
if [ "$REMOVE" = "true" ]; then
    set +e
    REMOVE_OUTPUT=$(docker rm "$CONTAINER_NAME" 2>&1)
    REMOVE_STATUS=$?
    set -e
    if [ $REMOVE_STATUS -ne 0 ]; then
        json_error "CONTAINER_REMOVE_FAILED" "$ID" "Container stopped but could not be removed" "$REMOVE_OUTPUT"
        exit 1
    fi
    json_success "$ID" "Container stopped and removed" "state" "removed"
else
    json_success "$ID" "Container stopped (use remove.sh to delete)" "state" "stopped"
fi

exit 0

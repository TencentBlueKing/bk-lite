#!/bin/bash

# webhookd mlops stop script
# 接收 JSON: {"id": "train-001"}

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

# 提取 id
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')

if [ -z "$ID" ]; then
    json_error "unknown" "Missing required field: id"
    exit 1
fi

# 容器名称
CONTAINER_NAME="${ID}"

# 检查容器是否存在
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    json_error "$ID" "Training job not found"
    exit 1
fi

# 停止并移除容器（5秒超时，避免 webhookd 总超时）
STOP_OUTPUT=$(docker stop --time=5 "$CONTAINER_NAME" 2>&1)
DOCKER_STATUS=$?

if [ $DOCKER_STATUS -eq 0 ]; then
    # 确保容器被删除（针对非--rm的容器）
    docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true
    json_success "$ID" "Training stopped successfully"
    exit 0
else
    json_error "$ID" "Failed to stop training" "$STOP_OUTPUT"
    exit 1
fi

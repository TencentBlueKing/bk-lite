#!/bin/bash

# webhookd mlops logs script
# 接收 JSON: {"id": "train-001", "lines": 100}

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

# 提取参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
LINES=$(echo "$JSON_DATA" | jq -r '.lines // "100"')

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

# 获取日志
LOGS=$(docker logs --tail "$LINES" "$CONTAINER_NAME" 2>&1)
DOCKER_STATUS=$?

if [ $DOCKER_STATUS -eq 0 ]; then
    # 转义日志内容为JSON
    LOGS_ESCAPED=$(echo "$LOGS" | jq -Rs .)
    echo "{\"status\":\"success\",\"id\":\"$ID\",\"logs\":$LOGS_ESCAPED}"
    exit 0
else
    json_error "$ID" "Failed to retrieve logs" "$LOGS"
    exit 1
fi

#!/bin/bash

# webhookd mlops status script
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

# 检查容器状态
CONTAINER_INFO=$(docker ps -a --filter "name=^${CONTAINER_NAME}$" --format '{{.Status}}' 2>/dev/null)

if [ -z "$CONTAINER_INFO" ]; then
    json_error "$ID" "Training job not found"
    exit 1
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

# 返回详细状态
echo "{\"status\":\"success\",\"id\":\"$ID\",\"container\":\"$CONTAINER_NAME\",\"state\":\"$STATUS\",\"detail\":\"$CONTAINER_INFO\"}"
exit 0

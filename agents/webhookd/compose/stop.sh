#!/bin/bash

# webhookd compose stop script
# 接收参数: id (通过 URL 参数或 JSON)

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 获取 ID（优先从 URL 参数，其次从 JSON）
if [ -n "$id" ]; then
    ID="$id"
elif [ -n "$1" ]; then
    ID=$(echo "$1" | jq -r '.id // empty' 2>/dev/null)
else
    json_error "" "No ID provided"
    exit 1
fi

if [ -z "$ID" ]; then
    json_error "" "Invalid ID"
    exit 1
fi

# 检查目录是否存在
COMPOSE_PATH="$COMPOSE_DIR/$ID"
if [ ! -d "$COMPOSE_PATH" ]; then
    json_error "$ID" "Compose directory not found"
    exit 1
fi

# 检查配置文件是否存在
COMPOSE_FILE="$COMPOSE_PATH/docker-compose.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    json_error "$ID" "Compose file not found"
    exit 1
fi

# 停止 docker-compose
cd "$COMPOSE_PATH"
STOP_OUTPUT=$(docker-compose down 2>&1)
STOP_STATUS=$?

if [ $STOP_STATUS -eq 0 ]; then
    json_success "$ID" "Successfully stopped"
else
    # 输出详细的停止日志
    echo "$STOP_OUTPUT" | logger
    json_error "$ID" "Failed to stop" "$STOP_OUTPUT"
fi
exit $STOP_STATUS

#!/bin/bash

# webhookd compose start script
# 启动已配置的服务
# 接收参数: id (通过 URL 参数或 JSON)

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 获取 ID（优先从 URL 参数，其次从 JSON）
if [ -n "$id" ]; then
    ID="$id"
elif [ -n "$1" ]; then
    ID=$(echo "$1" | jq -r '.id // empty')
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
    json_error "$ID" "Compose directory not found, please run setup first"
    exit 1
fi

# 检查配置文件是否存在
COMPOSE_FILE="$COMPOSE_PATH/docker-compose.yml"
if [ ! -f "$COMPOSE_FILE" ]; then
    json_error "$ID" "Compose file not found, please run setup first"
    exit 1
fi

# 启动 docker-compose
cd "$COMPOSE_PATH"
START_OUTPUT=$(docker-compose up -d 2>&1)
START_STATUS=$?

if [ $START_STATUS -eq 0 ]; then
    json_success "$ID" "Successfully started"
else
    # 输出详细的启动日志
    echo "$START_OUTPUT" | logger
    json_error "$ID" "Failed to start" "$START_OUTPUT"
fi
exit $START_STATUS
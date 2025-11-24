#!/bin/bash

# webhookd compose setup script
# 接收 JSON: {"id": "app-001", "compose": "...docker-compose配置..."}

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

# 提取 id 和 compose 配置
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
COMPOSE_CONFIG=$(echo "$JSON_DATA" | jq -r '.compose // empty')

if [ -z "$ID" ] || [ -z "$COMPOSE_CONFIG" ]; then
    json_error "${ID:-unknown}" "Missing required fields (id or compose)"
    exit 1
fi

# 检查目录是否存在
COMPOSE_PATH="$COMPOSE_DIR/$ID"
if [ ! -d "$COMPOSE_PATH" ]; then
    mkdir -p "$COMPOSE_PATH" 2>&1 | logger
fi

# 定义文件路径
COMPOSE_FILE="$COMPOSE_PATH/docker-compose.yml"

# 写入新配置
echo "$COMPOSE_CONFIG" > "$COMPOSE_FILE" 2>&1 | logger

# 校验 compose 配置
cd "$COMPOSE_PATH"
VALIDATION_OUTPUT=$(docker-compose config 2>&1)
VALIDATION_STATUS=$?

if [ $VALIDATION_STATUS -eq 0 ]; then
    json_success "$ID" "Configuration is valid" "file" "$COMPOSE_FILE"
    exit 0
else
    json_error "$ID" "Invalid configuration" "$VALIDATION_OUTPUT"
    exit 1
fi

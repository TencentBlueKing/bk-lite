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

# 校验资源标识并把路径限制在 compose 根目录内
if ! COMPOSE_PATH=$(get_compose_path "$ID"); then
    json_error "" "Invalid ID"
    exit 1
fi
if [ ! -d "$COMPOSE_PATH" ]; then
    if ! mkdir -- "$COMPOSE_PATH" && { [ ! -d "$COMPOSE_PATH" ] || [ -L "$COMPOSE_PATH" ]; }; then
        json_error "$ID" "Failed to create compose directory"
        exit 1
    fi
fi
if ! COMPOSE_PATH=$(get_compose_path "$ID"); then
    json_error "" "Invalid compose directory"
    exit 1
fi

# 定义文件路径
COMPOSE_FILE="$COMPOSE_PATH/docker-compose.yml"
if [ -L "$COMPOSE_FILE" ] || { [ -e "$COMPOSE_FILE" ] && [ ! -f "$COMPOSE_FILE" ]; }; then
    json_error "$ID" "Invalid compose file"
    exit 1
fi
TEMP_FILE=$(mktemp "$COMPOSE_PATH/.docker-compose.yml.XXXXXX")
cleanup() {
    rm -f -- "$TEMP_FILE"
}
trap cleanup EXIT

# 先在同目录临时文件中校验，成功后再以 rename 原子提交。
printf '%s\n' "$COMPOSE_CONFIG" > "$TEMP_FILE"

# 保留既有项目目录语义（.env、相对 build/env_file 路径等）。
cd "$COMPOSE_PATH"
if VALIDATION_OUTPUT=$(docker-compose -f "$TEMP_FILE" config 2>&1); then
    chmod 0644 "$TEMP_FILE"
    mv -f -- "$TEMP_FILE" "$COMPOSE_FILE"
    trap - EXIT
    json_success "$ID" "Configuration is valid" "file" "$COMPOSE_FILE"
    exit 0
else
    json_error "$ID" "Invalid configuration" "$VALIDATION_OUTPUT"
    exit 1
fi

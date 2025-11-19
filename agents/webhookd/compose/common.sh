#!/bin/bash

# webhookd compose 公共配置

# 加载上层公共函数
WEBHOOKD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$WEBHOOKD_DIR/common.sh"

# Compose 文件存储目录
COMPOSE_DIR="${COMPOSE_DIR:-/opt/webhookd/compose}"

# 确保目录存在
ensure_compose_dir() {
    mkdir -p "$COMPOSE_DIR"
}

# 验证 ID 是否有效
validate_id() {
    local id="$1"
    if [ -z "$id" ]; then
        return 1
    fi
    # 可以在这里添加更多验证规则，比如只允许字母数字和连字符
    if [[ ! "$id" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        return 1
    fi
    return 0
}

# 获取 compose 路径
get_compose_path() {
    local id="$1"
    echo "$COMPOSE_DIR/$id"
}

# 获取 compose 文件路径
get_compose_file() {
    local id="$1"
    echo "$COMPOSE_DIR/$id/docker-compose.yml"
}

# 返回列表响应（compose 专用）
json_list() {
    local json_array="$1"
    echo "{\"status\":\"success\",\"services\":$json_array}"
}

# 返回状态响应（compose 专用）
json_status() {
    local id="$1"
    local containers="$2"
    echo "{\"status\":\"success\",\"id\":\"$id\",\"containers\":$containers}"
}

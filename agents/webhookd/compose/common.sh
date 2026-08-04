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
    local compose_root
    local compose_path

    if ! validate_id "$id"; then
        return 1
    fi
    ensure_compose_dir || return 1
    compose_root=$(cd -P -- "$COMPOSE_DIR" && pwd) || return 1
    compose_path="$compose_root/$id"

    # 服务目录必须由 webhookd 自己管理，禁止借助符号链接跳出根目录。
    if [ -L "$compose_path" ] || { [ -e "$compose_path" ] && [ ! -d "$compose_path" ]; }; then
        return 1
    fi
    printf '%s\n' "$compose_path"
}

# 获取 compose 文件路径
get_compose_file() {
    local id="$1"
    local compose_path

    compose_path=$(get_compose_path "$id") || return 1
    printf '%s/docker-compose.yml\n' "$compose_path"
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

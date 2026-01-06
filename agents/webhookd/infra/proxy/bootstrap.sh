#!/bin/bash
set -euo pipefail

# ANSI escape codes for colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

set -a
source .env
set +a

# 配置参数
REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_PORT="${REMOTE_PORT:-4222}"
TIMEOUT="${TIMEOUT:-5}"
INSTALL_DIR="${INSTALL_DIR:-/opt/bk-lite/proxy}"
DOCKER_COMPOSE_CMD=""

# Function to log messages with colored output
log() {
    local level="$1"
    local message="$2"
    local color=""

    case "$level" in
        "INFO")
            color="$BLUE"
            ;;
        "WARNING")
            color="$YELLOW"
            ;;
        "ERROR")
            color="$RED"
            ;;
        "SUCCESS")
            color="$GREEN"
            ;;
        *)
            color="$NC"
            ;;
    esac

    echo -e "${color}[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $message${NC}"
}

# 检测 Docker Compose
check_docker_compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker-compose"
    elif docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE_CMD="docker compose"
    else
        log "ERROR" "未找到 docker-compose 或 docker compose 命令"
        return 1
    fi
    log "SUCCESS" "Docker Compose: $DOCKER_COMPOSE_CMD"
}

# 检测 TCP 连通性
check_tcp_connectivity() {
    local remote_host="$1"
    local remote_port="$2"
    local timeout="$3"
    
    if timeout "$timeout" bash -c "echo >/dev/tcp/$remote_host/$remote_port" 2>/dev/null; then
        log "SUCCESS" "TCP 连接: $remote_host:$remote_port"
    else
        log "ERROR" "TCP 连接失败: $remote_host:$remote_port"
        return 1
    fi
}

# 启动 compose 服务
start_compose() {
    log "INFO" "启动服务..."
    cd "$INSTALL_DIR" || { log "ERROR" "无法进入目录: $INSTALL_DIR"; return 1; }
    
    if ! $DOCKER_COMPOSE_CMD up -d; then
        log "ERROR" "服务启动失败"
        return 1
    fi
    log "SUCCESS" "服务启动完成"
}

# 检查服务状态
check_services() {
    log "INFO" "检查服务状态..."
    cd "$INSTALL_DIR" || return 1
    
    local failed=0
    while IFS= read -r line; do
        local name state
        name=$(echo "$line" | awk '{print $1}')
        state=$(echo "$line" | awk '{print $NF}')
        
        if [[ "$state" =~ ^(running|Up)$ ]]; then
            log "SUCCESS" "$name: $state"
        else
            log "ERROR" "$name: $state"
            failed=1
        fi
    done < <($DOCKER_COMPOSE_CMD ps --format "table {{.Name}}\t{{.State}}" 2>/dev/null | tail -n +2)
    
    return $failed
}

# Main execution
main() {
    check_docker_compose
    
    if [ -n "$REMOTE_HOST" ]; then
        check_tcp_connectivity "$REMOTE_HOST" "$REMOTE_PORT" "$TIMEOUT"
    fi
    
    start_compose
    
    sleep 3
    check_services
    
    log "SUCCESS" "部署完成"
}

main "$@"
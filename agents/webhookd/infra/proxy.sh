#!/bin/bash
set -euo pipefail

# 检测脚本模板
DETECT_SCRIPT_TEMPLATE=$(
    cat <<'EOF'
#!/bin/bash
set -euo pipefail

# ANSI escape codes for colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置参数
REMOTE_HOST="${REMOTE_HOST}"
REMOTE_PORT="${REMOTE_PORT}"
TIMEOUT="${TIMEOUT}"

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

# Function to check Docker Compose version and type
check_docker_compose() {
    local compose_version=""
    local cmd_type=""
    
    log "INFO" "开始检测 Docker Compose..."
    
    if command -v docker-compose >/dev/null 2>&1; then
        compose_version=$(docker-compose --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        cmd_type="docker-compose (standalone)"
        DOCKER_COMPOSE_CMD="docker-compose"
    elif docker compose version >/dev/null 2>&1; then
        compose_version=$(docker compose version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        cmd_type="docker compose (plugin)"
        DOCKER_COMPOSE_CMD="docker compose"
    else
        log "ERROR" "未找到 docker-compose 或 docker compose 命令"
        log "ERROR" "请安装 docker-compose 或将 docker 升级到最新版本"
        return 1
    fi
    
    if [ -z "$compose_version" ]; then
        log "ERROR" "无法获取 Docker Compose 版本信息"
        return 1
    fi
    
    log "SUCCESS" "Docker Compose 版本: $compose_version"
    log "SUCCESS" "Docker Compose 类型: $cmd_type"
    
    return 0
}

# Function to check TCP connectivity to remote service
check_tcp_connectivity() {
    local remote_host="$1"
    local remote_port="$2"
    local timeout="$3"
    
    log "INFO" "开始检测远端服务 TCP 连通性..."
    log "INFO" "目标地址: $remote_host:$remote_port"
    
    # 检测可用的连接测试工具
    if command -v nc >/dev/null 2>&1; then
        # 使用 nc (netcat) 测试连接
        if nc -z -w "$timeout" "$remote_host" "$remote_port" 2>/dev/null; then
            log "SUCCESS" "TCP 连接成功: $remote_host:$remote_port"
            return 0
        else
            log "ERROR" "TCP 连接失败: $remote_host:$remote_port"
            return 1
        fi
    elif command -v timeout >/dev/null 2>&1 && command -v bash >/dev/null 2>&1; then
        # 使用 bash 内置的 /dev/tcp 测试连接
        if timeout "$timeout" bash -c "echo >/dev/tcp/$remote_host/$remote_port" 2>/dev/null; then
            log "SUCCESS" "TCP 连接成功: $remote_host:$remote_port"
            return 0
        else
            log "ERROR" "TCP 连接失败: $remote_host:$remote_port"
            return 1
        fi
    elif command -v curl >/dev/null 2>&1; then
        # 使用 curl 测试连接
        if curl --connect-timeout "$timeout" -s "telnet://$remote_host:$remote_port" >/dev/null 2>&1; then
            log "SUCCESS" "TCP 连接成功: $remote_host:$remote_port"
            return 0
        else
            log "ERROR" "TCP 连接失败: $remote_host:$remote_port"
            return 1
        fi
    else
        log "ERROR" "未找到可用的连接测试工具 (nc/timeout/curl)"
        log "ERROR" "请安装 netcat 或 curl"
        return 1
    fi
}

# Main execution
main() {
    local exit_code=0
    
    log "INFO" "=========================================="
    log "INFO" "开始执行环境检测..."
    log "INFO" "=========================================="
    
    # 1. 检测 Docker Compose 版本和类型
    if ! check_docker_compose; then
        log "ERROR" "Docker Compose 检测失败"
        exit_code=1
    fi
    
    echo ""
    
    # 2. 检测远端服务 TCP 连通性
    if [ -n "$REMOTE_HOST" ]; then
        if ! check_tcp_connectivity "$REMOTE_HOST" "$REMOTE_PORT" "$TIMEOUT"; then
            log "ERROR" "远端服务 TCP 连通性检测失败"
            exit_code=1
        fi
    else
        log "WARNING" "未指定远端服务地址，跳过 TCP 连通性检测"
    fi
    
    echo ""
    log "INFO" "=========================================="
    if [ $exit_code -eq 0 ]; then
        log "SUCCESS" "所有检测完成"
    else
        log "ERROR" "检测过程中存在错误"
    fi
    log "INFO" "=========================================="
    
    exit $exit_code
}

main "$@"
EOF
)

# 返回成功的 JSON 响应（支持多行内容）
json_success() {
    local id="$1"
    local message="$2"
    shift 2
    
    # 使用 jq 构建 JSON，确保正确转义
    local json
    json=$(jq -n --arg id "$id" --arg message "$message" '{status: "success", id: $id, message: $message}')
    
    # 添加额外的字段
    while [ $# -gt 0 ]; do
        json=$(echo "$json" | jq --arg key "$1" --arg value "$2" '. + {($key): $value}')
        shift 2
    done
    
    echo "$json"
}

# 返回错误的 JSON 响应
json_error() {
    local id="$1"
    local message="$2"
    local error="${3:-}"
    
    if [ -n "$error" ]; then
        jq -n --arg id "$id" --arg message "$message" --arg error "$error" \
            '{status: "error", id: $id, message: $message, error: $error}'
    else
        jq -n --arg id "$id" --arg message "$message" \
            '{status: "error", id: $id, message: $message}'
    fi
}

# 参数校验函数
validate_param() {
    local param_name="$1"
    local param_value="$2"
    local validation_type="$3"
    local node_id="${4:-}"
    
    case "$validation_type" in
        required)
            [ -n "$param_value" ] || { json_error "$node_id" "Missing required parameter: $param_name"; exit 1; }
            ;;
        url)
            [ -z "$param_value" ] || echo "$param_value" | grep -qE '^https?://' || \
                { json_error "$node_id" "Invalid $param_name format. Must start with http:// or https://"; exit 1; }
            ;;
        positive_int)
            echo "$param_value" | grep -qE '^[0-9]+$' || \
                { json_error "$node_id" "Invalid $param_name: must be a positive integer"; exit 1; }
            ;;
    esac
}

# 检查依赖和输入数据
command -v jq &> /dev/null || \
    { echo '{"status": "error", "message": "jq command not found. Please install jq to run this script."}' >&2; exit 1; }

JSON_DATA="${1:-$(cat)}"
[ -n "$JSON_DATA" ] || { json_error "" "No input data provided"; exit 1; }
echo "$JSON_DATA" | jq empty 2>/dev/null || { json_error "" "Invalid JSON format"; exit 1; }

# 提取所有参数
NODE_ID=$(echo "$JSON_DATA" | jq -r '.node_id // empty')
REMOTE_HOST=$(echo "$JSON_DATA" | jq -r '.remote_host // empty')
REMOTE_PORT=$(echo "$JSON_DATA" | jq -r '.remote_port // "7422"')
TIMEOUT=$(echo "$JSON_DATA" | jq -r '.timeout // "5"')

# 参数校验
validate_param "node_id" "$NODE_ID" "required"
validate_param "remote_port" "$REMOTE_PORT" "positive_int" "$NODE_ID"
validate_param "timeout" "$TIMEOUT" "positive_int" "$NODE_ID"

# 生成检测脚本
DETECT_SCRIPT="$DETECT_SCRIPT_TEMPLATE"

declare -A replacements=(
    [REMOTE_HOST]="$REMOTE_HOST"
    [REMOTE_PORT]="$REMOTE_PORT"
    [TIMEOUT]="$TIMEOUT"
)

for key in "${!replacements[@]}"; do
    DETECT_SCRIPT="${DETECT_SCRIPT//\$\{$key\}/${replacements[$key]}}"
done

# 返回成功的 JSON 响应，包含生成的检测脚本
json_success "$NODE_ID" "Detection script generated successfully" "detect_script" "$DETECT_SCRIPT"
exit 0
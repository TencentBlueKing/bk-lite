#!/bin/bash
set -euo pipefail

# 检测脚本模板
DETECT_SCRIPT_TEMPLATE=$(
    cat <<'EOF'
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
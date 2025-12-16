#!/bin/bash

# webhookd 公共函数库
# 提供跨 compose/kubernetes 等多个子目录共用的工具函数

# 返回成功的 JSON 响应
json_success() {
    local id="$1"
    local message="$2"
    shift 2
    
    local json="{\"status\":\"success\",\"id\":\"$id\",\"message\":\"$message\""
    
    # 添加额外的字段
    while [ $# -gt 0 ]; do
        json="$json,\"$1\":\"$2\""
        shift 2
    done
    
    json="$json}"
    echo "$json"
}

# 返回错误的 JSON 响应
json_error() {
    local id="$1"
    local message="$2"
    local error="${3:-}"
    
    local json="{\"status\":\"error\",\"id\":\"$id\",\"message\":\"$message\""
    
    if [ -n "$error" ]; then
        # 转义错误信息中的特殊字符
        error=$(echo "$error" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr '\n' ' ')
        json="$json,\"error\":\"$error\""
    fi
    
    json="$json}"
    echo "$json"
}

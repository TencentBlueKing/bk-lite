#!/bin/bash

# MLOps 公共配置和函数

# 工作目录
MLOPS_DIR="${MLOPS_DIR:-/opt/webhookd/mlops}"

# 训练镜像（如果没有从 JSON 传入，使用此默认值）
TRAIN_IMAGE="${TRAIN_IMAGE:-classify-timeseries:latest}"

# 日志函数
logger() {
    while IFS= read -r line; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line" >&2
    done
}

# JSON 成功响应
json_success() {
    local id="$1"
    local message="$2"
    local key="$3"
    local value="$4"
    
    if [ -n "$key" ] && [ -n "$value" ]; then
        echo "{\"status\":\"success\",\"id\":\"$id\",\"message\":\"$message\",\"$key\":\"$value\"}"
    else
        echo "{\"status\":\"success\",\"id\":\"$id\",\"message\":\"$message\"}"
    fi
}

# JSON 错误响应
json_error() {
    local code="$1"
    local id="$2"
    local message="$3"
    local detail="$4"
    
    if [ -n "$detail" ]; then
        # 转义双引号和换行符
        detail=$(echo "$detail" | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"status\":\"error\",\"code\":\"$code\",\"id\":\"$id\",\"message\":\"$message\",\"detail\":\"$detail\"}"
    else
        echo "{\"status\":\"error\",\"code\":\"$code\",\"id\":\"$id\",\"message\":\"$message\"}"
    fi
}

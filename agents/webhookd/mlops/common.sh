#!/bin/bash

# MLOps 公共配置和函数

# 工作目录
MLOPS_DIR="${MLOPS_DIR:-/opt/webhookd/mlops}"

# 固定端口配置
MINIO_PORT=9000
MLFLOW_PORT=15000

# 训练镜像
TRAIN_IMAGE="${TRAIN_IMAGE:-classify-timeseries:latest}"

# 获取Docker网关IP（默认bridge网络）
get_docker_gateway() {
    docker network inspect bridge -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null
}

# 构建完整的服务endpoint
get_minio_endpoint() {
    local gateway_ip=$(get_docker_gateway)
    echo "http://${gateway_ip}:${MINIO_PORT}"
}

get_mlflow_endpoint() {
    local gateway_ip=$(get_docker_gateway)
    echo "http://${gateway_ip}:${MLFLOW_PORT}"
}

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
    local id="$1"
    local message="$2"
    local detail="$3"
    
    if [ -n "$detail" ]; then
        # 转义双引号和换行符
        detail=$(echo "$detail" | sed 's/"/\\"/g' | tr '\n' ' ')
        echo "{\"status\":\"error\",\"id\":\"$id\",\"message\":\"$message\",\"detail\":\"$detail\"}"
    else
        echo "{\"status\":\"error\",\"id\":\"$id\",\"message\":\"$message\"}"
    fi
}

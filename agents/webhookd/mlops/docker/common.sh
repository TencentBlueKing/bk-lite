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

# GPU 配置函数
# 参数: $1 = gpu 配置值 (all|none|0|0,1|... 或空)
# 返回: GPU_ARGS 变量（Docker 命令行参数）
# 
# 行为：
#   - 未传递（空/null）：不添加任何 GPU 参数（Docker 默认行为）
#   - "all"：使用所有 GPU
#   - "none"：明确禁用 GPU（不添加参数，等同于未传递）
#   - "0" 或 "0,1"：指定 GPU 设备
setup_gpu_args() {
    local gpu_config="$1"
    GPU_ARGS=""
    
    # 未传递或为 null：不添加 GPU 参数
    if [ -z "$gpu_config" ] || [ "$gpu_config" = "null" ]; then
        echo "[INFO] GPU parameter not specified, using Docker default behavior" >&2
        return
    fi
    
    case "$gpu_config" in
        "all")
            # 使用所有 GPU
            GPU_ARGS="--gpus all"
            echo "[INFO] Using all GPUs" >&2
            ;;
        "none")
            # 明确禁用 GPU（不添加参数）
            echo "[INFO] GPU explicitly disabled, using CPU only" >&2
            ;;
        *)
            # 指定设备：0 或 0,1 等
            GPU_ARGS="--gpus '\"device=${gpu_config}\"'"
            echo "[INFO] Using GPU devices: $gpu_config" >&2
            ;;
    esac
}

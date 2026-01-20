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

# 检查 GPU 是否可用
check_gpu_available() {
    # 检查是否有 NVIDIA Docker Runtime
    docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi >/dev/null 2>&1
}

# Device 配置函数
# 参数: $1 = device 配置值 (cpu|gpu|auto 或空)
# 返回: DEVICE_ARGS 变量（Docker 命令行参数）
# 
# 行为：
#   - 未传递（空/null）或 "cpu"：不添加 GPU 参数（CPU 模式）
#   - "auto"：自动检测，有 GPU 则使用，无 GPU 则 CPU
#   - "gpu"：必须使用 GPU，无 GPU 则报错
setup_device_args() {
    local device="$1"
    DEVICE_ARGS=""
    
    # 未传递、null 或 cpu：默认 CPU 模式
    if [ -z "$device" ] || [ "$device" = "null" ] || [ "$device" = "cpu" ]; then
        echo "[INFO] Device: CPU" >&2
        return 0
    fi
    
    case "$device" in
        "auto")
            # 自动检测 GPU
            echo "[INFO] Device: auto (detecting GPU availability...)" >&2
            if check_gpu_available; then
                DEVICE_ARGS="--gpus all"
                echo "[INFO] GPU detected, using GPU mode" >&2
            else
                echo "[INFO] No GPU detected, using CPU mode" >&2
            fi
            return 0
            ;;
        "gpu")
            # 必须使用 GPU
            echo "[INFO] Device: GPU (required)" >&2
            if ! check_gpu_available; then
                echo "[ERROR] GPU required but not available" >&2
                return 1
            fi
            DEVICE_ARGS="--gpus all"
            echo "[INFO] GPU available, using GPU mode" >&2
            return 0
            ;;
        *)
            echo "[ERROR] Invalid device parameter: $device (expected: cpu, gpu, auto)" >&2
            return 1
            ;;
    esac
}

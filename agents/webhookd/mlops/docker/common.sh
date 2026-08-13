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
        jq -cn \
            --arg id "$id" \
            --arg message "$message" \
            --arg key "$key" \
            --arg value "$value" \
            '{status:"success", id:$id, message:$message} + {($key):$value}'
    else
        jq -cn \
            --arg id "$id" \
            --arg message "$message" \
            '{status:"success", id:$id, message:$message}'
    fi
}

# JSON 错误响应
json_error() {
    local code="$1"
    local id="$2"
    local message="$3"
    local detail="$4"
    
    if [ -n "$detail" ]; then
        jq -cn \
            --arg code "$code" \
            --arg id "$id" \
            --arg message "$message" \
            --arg detail "$detail" \
            '{status:"error", code:$code, id:$id, message:$message, detail:$detail}'
    else
        jq -cn \
            --arg code "$code" \
            --arg id "$id" \
            --arg message "$message" \
            '{status:"error", code:$code, id:$id, message:$message}'
    fi
}

# 通过可选 runner 执行 GPU 探针；serve 会传入共享启动预算 runner，train
# 保持原调用方式。Serving 缺镜像时显式、受预算约束地拉取，再禁止 docker
# run 隐式拉取；训练链不传 runner，保持原有按需拉取行为。
run_gpu_probe_command() {
    local runner="$1"
    shift
    if [ -n "$runner" ]; then
        "$runner" "$@"
    else
        "$@"
    fi
}

# 检查 GPU 是否可用
check_gpu_available() {
    local runner="$1"
    local probe_id="${2:-$$}"
    GPU_PROBE_CONTAINER_NAME="bk-lite-gpu-probe-${probe_id}"

    if [ -n "$runner" ]; then
        if ! run_gpu_probe_command "$runner" docker image inspect nvidia/cuda:11.0-base >/dev/null 2>&1; then
            run_gpu_probe_command "$runner" docker pull nvidia/cuda:11.0-base >/dev/null 2>&1 || return 1
        fi
        run_gpu_probe_command "$runner" docker run --rm --pull never \
            --name "$GPU_PROBE_CONTAINER_NAME" \
            --label "bk-lite.startup-id=$probe_id" \
            --gpus all nvidia/cuda:11.0-base nvidia-smi >/dev/null 2>&1
        return $?
    fi

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
    local runner="$2"
    local probe_id="$3"
    DEVICE_ARGS=""
    GPU_PROBE_CONTAINER_NAME=""
    
    # 未传递、null 或 cpu：默认 CPU 模式
    if [ -z "$device" ] || [ "$device" = "null" ] || [ "$device" = "cpu" ]; then
        return 0
    fi
    
    case "$device" in
        "auto")
            # 自动检测 GPU
            if check_gpu_available "$runner" "$probe_id"; then
                DEVICE_ARGS="--gpus all"
            fi
            return 0
            ;;
        "gpu")
            # 必须使用 GPU
            if ! check_gpu_available "$runner" "$probe_id"; then
                return 1
            fi
            DEVICE_ARGS="--gpus all"
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

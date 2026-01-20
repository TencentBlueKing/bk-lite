#!/bin/bash

# MLOps Kubernetes 公共配置和函数

# 工作目录
MLOPS_DIR="${MLOPS_DIR:-/opt/webhookd/mlops}"

# Kubernetes 命名空间（默认）
KUBERNETES_NAMESPACE="${KUBERNETES_NAMESPACE:-mlops}"

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

# GPU 配置函数（Kubernetes 版本）
# 参数: $1 = gpu 配置值 (all|none|0|0,1|count:2 或空)
# 返回: GPU_RESOURCE 变量（Kubernetes resources.limits）
# 
# 行为：
#   - 未传递（空/null）：不添加任何 GPU 限制
#   - "all"：nvidia.com/gpu: 1（Kubernetes 中需要指定具体数量）
#   - "none"：明确禁用 GPU
#   - "count:N"：nvidia.com/gpu: N
#   - "0" 或 "0,1"：转换为 count（计算逗号分隔的设备数）
setup_gpu_resources() {
    local gpu_config="$1"
    GPU_RESOURCE=""
    GPU_LIMIT_YAML=""
    
    # 未传递或为 null：不添加 GPU 限制
    if [ -z "$gpu_config" ] || [ "$gpu_config" = "null" ]; then
        echo "[INFO] GPU parameter not specified, no GPU resources requested" >&2
        return
    fi
    
    case "$gpu_config" in
        "all")
            # Kubernetes 不支持 "all"，默认请求 1 个 GPU
            GPU_RESOURCE="1"
            GPU_LIMIT_YAML="            nvidia.com/gpu: \"1\""
            echo "[INFO] Requesting 1 GPU (Kubernetes does not support 'all', defaulting to 1)" >&2
            ;;
        "none")
            # 明确禁用 GPU
            echo "[INFO] GPU explicitly disabled, no GPU resources requested" >&2
            ;;
        count:*)
            # 指定数量：count:2
            GPU_RESOURCE="${gpu_config#count:}"
            GPU_LIMIT_YAML="            nvidia.com/gpu: \"${GPU_RESOURCE}\""
            echo "[INFO] Requesting ${GPU_RESOURCE} GPU(s)" >&2
            ;;
        *,*)
            # 设备列表：0,1 -> 计算数量
            GPU_COUNT=$(echo "$gpu_config" | tr ',' '\n' | wc -l)
            GPU_RESOURCE="$GPU_COUNT"
            GPU_LIMIT_YAML="            nvidia.com/gpu: \"${GPU_RESOURCE}\""
            echo "[INFO] Requesting ${GPU_RESOURCE} GPU(s) (parsed from device list: $gpu_config)" >&2
            ;;
        *)
            # 单个设备或数字：0 或 1
            if [[ "$gpu_config" =~ ^[0-9]+$ ]]; then
                GPU_RESOURCE="1"
                GPU_LIMIT_YAML="            nvidia.com/gpu: \"1\""
                echo "[INFO] Requesting 1 GPU (device: $gpu_config)" >&2
            else
                echo "[WARN] Invalid GPU config: $gpu_config, ignoring" >&2
            fi
            ;;
    esac
}

# 确保命名空间存在
ensure_namespace() {
    local namespace="$1"
    
    if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
        echo "[INFO] Creating namespace: $namespace" >&2
        kubectl create namespace "$namespace" >/dev/null 2>&1 || {
            echo "[ERROR] Failed to create namespace: $namespace" >&2
            return 1
        }
    fi
}

# 生成 Secret 名称（基于 ID）
generate_secret_name() {
    local id="$1"
    echo "${id}-minio-secret"
}

# 创建 MinIO Secret（如果不存在）
create_minio_secret() {
    local namespace="$1"
    local secret_name="$2"
    local access_key="$3"
    local secret_key="$4"
    
    # 检查 Secret 是否已存在
    if kubectl get secret "$secret_name" -n "$namespace" >/dev/null 2>&1; then
        echo "[INFO] Secret $secret_name already exists in namespace $namespace" >&2
        return 0
    fi
    
    echo "[INFO] Creating secret: $secret_name" >&2
    kubectl create secret generic "$secret_name" \
        --from-literal=access_key="$access_key" \
        --from-literal=secret_key="$secret_key" \
        -n "$namespace" >/dev/null 2>&1 || {
        echo "[ERROR] Failed to create secret: $secret_name" >&2
        return 1
    }
}

# 删除 Secret（如果存在）
delete_secret() {
    local namespace="$1"
    local secret_name="$2"
    
    if kubectl get secret "$secret_name" -n "$namespace" >/dev/null 2>&1; then
        echo "[INFO] Deleting secret: $secret_name" >&2
        kubectl delete secret "$secret_name" -n "$namespace" >/dev/null 2>&1 || true
    fi
}

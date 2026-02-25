#!/bin/bash

# MLOps Kubernetes 公共配置和函数

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

# 检查 Kubernetes 集群是否有 GPU 节点
check_gpu_available_k8s() {
    local gpu_count=$(kubectl get nodes -o json 2>/dev/null | \
        jq '[.items[].status.capacity["nvidia.com/gpu"] | select(. != null)] | length' 2>/dev/null || echo "0")
    [ "$gpu_count" -gt 0 ]
}

# Device 配置函数（Kubernetes 版本）
# 参数: $1 = device 配置值 (cpu|gpu|auto 或空)
# 返回: DEVICE_LIMIT_YAML 变量（Kubernetes resources.limits）
# 
# 行为：
#   - 未传递（空/null）或 "cpu"：不添加 GPU 限制（CPU 模式）
#   - "auto"：自动检测，有 GPU 节点则请求 1 个，无 GPU 节点则 CPU
#   - "gpu"：必须使用 GPU，无 GPU 节点则报错
setup_device_resources() {
    local device="$1"
    DEVICE_LIMIT_YAML=""
    
    # 未传递、null 或 cpu：默认 CPU 模式
    if [ -z "$device" ] || [ "$device" = "null" ] || [ "$device" = "cpu" ]; then
        echo "[INFO] Device: CPU" >&2
        return 0
    fi
    
    case "$device" in
        "auto")
            # 自动检测 GPU
            echo "[INFO] Device: auto (detecting GPU availability...)" >&2
            if check_gpu_available_k8s; then
                DEVICE_LIMIT_YAML="            nvidia.com/gpu: \"1\""
                echo "[INFO] GPU nodes detected, requesting 1 GPU" >&2
            else
                echo "[INFO] No GPU nodes detected, using CPU mode" >&2
            fi
            return 0
            ;;
        "gpu")
            # 必须使用 GPU
            echo "[INFO] Device: GPU (required)" >&2
            if ! check_gpu_available_k8s; then
                echo "[ERROR] GPU required but no GPU nodes found in cluster" >&2
                return 1
            fi
            DEVICE_LIMIT_YAML="            nvidia.com/gpu: \"1\""
            echo "[INFO] GPU nodes available, requesting 1 GPU" >&2
            return 0
            ;;
        *)
            echo "[ERROR] Invalid device parameter: $device (expected: cpu, gpu, auto)" >&2
            return 1
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

# 将 ID 转换为 K8s DNS-1123 合规名称
# 大写转小写、下划线转连字符
sanitize_k8s_name() {
    local name="$1"
    echo "$name" | tr '[:upper:]' '[:lower:]' | tr '_' '-'
}

# 生成 Secret 名称（基于 sanitized ID）
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

#!/bin/bash

# MLOps Kubernetes 公共配置和函数

# Kubernetes 命名空间（默认）
KUBERNETES_NAMESPACE="${KUBERNETES_NAMESPACE:-mlops}"

# 当前 Pod 所在的命名空间（用于将服务短名称解析为 FQDN）
# 优先使用环境变量，其次读取 ServiceAccount 挂载，最终回退为 default
if [ -n "${POD_NAMESPACE:-}" ]; then
    _CURRENT_NAMESPACE="$POD_NAMESPACE"
elif [ -f /var/run/secrets/kubernetes.io/serviceaccount/namespace ]; then
    _CURRENT_NAMESPACE=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
else
    _CURRENT_NAMESPACE="default"
fi

# 训练镜像（如果没有从 JSON 传入，使用此默认值）
TRAIN_IMAGE="${TRAIN_IMAGE:-classify-timeseries:latest}"

# 日志函数（注意：webhookd 合并 stdout/stderr，日志会污染 HTTP 响应，此函数仅供调试使用）
# 生产环境中不应使用此函数
logger() {
    while IFS= read -r line; do
        # 日志被禁用以避免污染 HTTP 响应
        # echo "[$(date '+%Y-%m-%d %H:%M:%S')] $line" >&2
        :
    done
}

# 将服务 URL 中的短名称 host 解析为 K8s FQDN
# 例: http://minio:9000 → http://minio.bklite-prod.svc.cluster.local:9000
# 如果 host 已包含 '.'（如 FQDN 或 IP），则不做转换
resolve_endpoint_fqdn() {
    local url="$1"
    local ns="${2:-$_CURRENT_NAMESPACE}"

    # 提取 scheme（http:// 或 https://）
    local scheme="${url%%://*}"
    local rest="${url#*://}"

    # 提取 host:port 部分（去掉路径）
    local host_port="${rest%%/*}"
    local path="/${rest#*/}"
    # 如果没有路径部分，path 会等于 /rest 本身，修正
    if [ "$rest" = "$host_port" ]; then
        path=""
    fi

    # 分离 host 和 port
    local host="${host_port%%:*}"
    local port=""
    if [ "$host_port" != "$host" ]; then
        port=":${host_port#*:}"
    fi

    # 如果 host 不含 '.'，说明是短名称，需要补全
    case "$host" in
        *.*)
            # 已经是 FQDN 或 IP，原样返回
            echo "$url"
            ;;
        *)
            echo "${scheme}://${host}.${ns}.svc.cluster.local${port}${path}"
            ;;
    esac
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
        # Device: CPU (日志被禁用以避免污染 HTTP 响应)
        return 0
    fi
    
    case "$device" in
        "auto")
            # 自动检测 GPU
            if check_gpu_available_k8s; then
                DEVICE_LIMIT_YAML="            nvidia.com/gpu: \"1\""
                # GPU nodes detected, requesting 1 GPU
            fi
            # else: No GPU nodes detected, using CPU mode
            return 0
            ;;
        "gpu")
            # 必须使用 GPU
            if ! check_gpu_available_k8s; then
                # GPU required but no GPU nodes found - 返回错误
                return 1
            fi
            DEVICE_LIMIT_YAML="            nvidia.com/gpu: \"1\""
            return 0
            ;;
        *)
            # Invalid device parameter
            return 1
            ;;
    esac
}

# 确保命名空间存在
ensure_namespace() {
    local namespace="$1"
    
    if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
        # Creating namespace (日志被禁用)
        kubectl create namespace "$namespace" >/dev/null 2>&1 || {
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
        # Secret already exists (日志被禁用)
        return 0
    fi
    
    # Creating secret (日志被禁用)
    kubectl create secret generic "$secret_name" \
        --from-literal=access_key="$access_key" \
        --from-literal=secret_key="$secret_key" \
        -n "$namespace" >/dev/null 2>&1 || {
        return 1
    }
}

# 为 Secret 添加 ownerReference，使其跟随 Job 自动删除
# 参数: $1=namespace, $2=secret_name, $3=owner_kind, $4=owner_name, $5=owner_uid
set_secret_owner() {
    local namespace="$1"
    local secret_name="$2"
    local owner_kind="$3"
    local owner_name="$4"
    local owner_uid="$5"
    
    kubectl patch secret "$secret_name" -n "$namespace" --type='merge' -p "{
        \"metadata\": {
            \"ownerReferences\": [{
                \"apiVersion\": \"batch/v1\",
                \"kind\": \"$owner_kind\",
                \"name\": \"$owner_name\",
                \"uid\": \"$owner_uid\",
                \"blockOwnerDeletion\": true
            }]
        }
    }" >/dev/null 2>&1 || {
        return 1
    }
}

# 删除 Secret（如果存在）
delete_secret() {
    local namespace="$1"
    local secret_name="$2"
    
    if kubectl get secret "$secret_name" -n "$namespace" >/dev/null 2>&1; then
        # Deleting secret (日志被禁用)
        kubectl delete secret "$secret_name" -n "$namespace" >/dev/null 2>&1 || true
    fi
}

#!/bin/bash

# webhookd mlops serve script (Kubernetes)
# 接收 JSON: {"id": "serving-001", "mlflow_tracking_uri": "http://mlflow.default.svc.cluster.local:15000", "mlflow_model_uri": "models:/model/1", "train_image": "classify-timeseries:latest", "workers": 2, "namespace": "mlops", "port": 30000, "service_type": "NodePort", "device": "auto|cpu|gpu"}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh" || {
    echo '{"status":"error","code":"COMMON_SH_LOAD_FAILED","message":"Failed to load common.sh"}'
    exit 1
}

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "INVALID_JSON" "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 检查 jq 是否可用
if ! command -v jq >/dev/null 2>&1; then
    json_error "JQ_NOT_FOUND" "" "jq command not found"
    exit 1
fi

# 检查 kubectl 是否可用
if ! command -v kubectl >/dev/null 2>&1; then
    json_error "KUBECTL_NOT_FOUND" "" "kubectl command not found"
    exit 1
fi

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null) || {
    json_error "JSON_PARSE_FAILED" "" "Failed to parse JSON data"
    exit 1
}
MLFLOW_TRACKING_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_tracking_uri // empty')
MLFLOW_MODEL_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_model_uri // empty')
WORKERS=$(echo "$JSON_DATA" | jq -r '.workers // "2"')
PORT=$(echo "$JSON_DATA" | jq -r '.port // empty')
NAMESPACE=$(echo "$JSON_DATA" | jq -r '.namespace // empty')
SERVICE_TYPE=$(echo "$JSON_DATA" | jq -r '.service_type // "NodePort"')
TRAIN_IMAGE=$(echo "$JSON_DATA" | jq -r '.train_image // empty')
DEVICE=$(echo "$JSON_DATA" | jq -r '.device // empty')
REPLICAS=$(echo "$JSON_DATA" | jq -r '.replicas // "1"')

# 使用默认命名空间（如果未指定）
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="$KUBERNETES_NAMESPACE"
fi

# 验证必需参数
if [ -z "$ID" ] || [ -z "$MLFLOW_TRACKING_URI" ] || [ -z "$MLFLOW_MODEL_URI" ]; then
    json_error "MISSING_REQUIRED_FIELD" "${ID:-unknown}" "Missing required fields (id, mlflow_tracking_uri, mlflow_model_uri)"
    exit 1
fi

if [ -z "$TRAIN_IMAGE" ]; then
    json_error "MISSING_TRAIN_IMAGE" "$ID" "Missing required field: train_image"
    exit 1
fi

# 将服务短名称解析为 FQDN（跨 namespace 访问时必需）
MLFLOW_TRACKING_URI=$(resolve_endpoint_fqdn "$MLFLOW_TRACKING_URI")

# Deployment/Service 名称（Kubernetes 资源名称必须符合 DNS-1123 标准）
K8S_NAME=$(sanitize_k8s_name "$ID")
DEPLOYMENT_NAME="${K8S_NAME}"
SERVICE_NAME="${K8S_NAME}-svc"

# 确保命名空间存在
ensure_namespace "$NAMESPACE" || {
    json_error "NAMESPACE_CREATION_FAILED" "$ID" "Failed to create namespace: $NAMESPACE"
    exit 1
}

# 检查 Deployment 是否已存在
if kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    # 检查 Deployment 状态
    READY_REPLICAS=$(kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    DESIRED_REPLICAS=$(kubectl get deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    
    if [ "$READY_REPLICAS" = "$DESIRED_REPLICAS" ] && [ "$READY_REPLICAS" != "0" ]; then
        json_error "DEPLOYMENT_ALREADY_EXISTS" "$ID" "Deployment already exists and is running" "Ready: $READY_REPLICAS/$DESIRED_REPLICAS. Use remove.sh or stop.sh to delete it first."
    else
        json_error "DEPLOYMENT_ALREADY_EXISTS" "$ID" "Deployment already exists but not ready" "Ready: $READY_REPLICAS/$DESIRED_REPLICAS. Use remove.sh to delete it first."
    fi
    exit 1
fi

# 用户指定端口时检查 NodePort 范围和占用
if [ -n "$PORT" ] && [ "$SERVICE_TYPE" = "NodePort" ]; then
    # 校验 NodePort 范围（默认 30000-32767）
    if [ "$PORT" -lt 30000 ] || [ "$PORT" -gt 32767 ]; then
        json_error "INVALID_NODEPORT" "$ID" "NodePort $PORT is not in valid range (30000-32767)"
        exit 1
    fi
    # 检查端口是否被占用
    EXISTING_SVC=$(kubectl get svc --all-namespaces -o json 2>/dev/null | jq -r ".items[] | select(.spec.ports[]?.nodePort == $PORT) | .metadata.name" 2>/dev/null || echo "")
    if [ -n "$EXISTING_SVC" ]; then
        json_error "PORT_IN_USE" "$ID" "NodePort $PORT is already in use by service: $EXISTING_SVC. Please choose a different port or wait for the previous service to be fully deleted."
        exit 1
    fi
fi

# 容器内固定端口 3000
CONTAINER_PORT="3000"

# 配置设备资源
setup_device_resources "$DEVICE" || {
    json_error "DEVICE_SETUP_FAILED" "$ID" "Failed to setup device: GPU required but not available"
    exit 1
}

# 生成 Kubernetes Deployment YAML
DEPLOYMENT_YAML=$(cat <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${DEPLOYMENT_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: mlops-serve
    service-id: ${ID}
spec:
  replicas: ${REPLICAS}
  selector:
    matchLabels:
      app: mlops-serve
      service-id: ${ID}
  template:
    metadata:
      labels:
        app: mlops-serve
        service-id: ${ID}
    spec:
      containers:
      - name: serve
        image: ${TRAIN_IMAGE}
        ports:
        - containerPort: ${CONTAINER_PORT}
          name: http
          protocol: TCP
        env:
        - name: BENTOML_HOST
          value: "0.0.0.0"
        - name: BENTOML_PORT
          value: "${CONTAINER_PORT}"
        - name: MODEL_SOURCE
          value: "mlflow"
        - name: MLFLOW_TRACKING_URI
          value: "${MLFLOW_TRACKING_URI}"
        - name: MLFLOW_MODEL_URI
          value: "${MLFLOW_MODEL_URI}"
        - name: WORKERS
          value: "${WORKERS}"
        - name: ALLOW_DUMMY_FALLBACK
          value: "false"
        livenessProbe:
          httpGet:
            path: /healthz
            port: ${CONTAINER_PORT}
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /readyz
            port: ${CONTAINER_PORT}
          initialDelaySeconds: 10
          periodSeconds: 5
EOF
)

# 添加设备资源限制（如果配置了）
if [ -n "$DEVICE_LIMIT_YAML" ]; then
    DEPLOYMENT_YAML=$(cat <<EOF
${DEPLOYMENT_YAML}
        resources:
          limits:
${DEVICE_LIMIT_YAML}
          requests:
${DEVICE_LIMIT_YAML}
EOF
)
fi

# 生成 Kubernetes Service YAML
SERVICE_YAML=$(cat <<EOF
---
apiVersion: v1
kind: Service
metadata:
  name: ${SERVICE_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: mlops-serve
    service-id: ${ID}
spec:
  type: ${SERVICE_TYPE}
  selector:
    app: mlops-serve
    service-id: ${ID}
  ports:
  - protocol: TCP
    port: ${CONTAINER_PORT}
    targetPort: ${CONTAINER_PORT}
EOF
)

# 如果指定了端口且使用 NodePort，添加 nodePort
if [ -n "$PORT" ] && [ "$SERVICE_TYPE" = "NodePort" ]; then
    SERVICE_YAML=$(cat <<EOF
${SERVICE_YAML}
    nodePort: ${PORT}
EOF
)
fi

# 合并 YAML
FULL_YAML=$(cat <<EOF
${DEPLOYMENT_YAML}
${SERVICE_YAML}
EOF
)

# 清理函数：删除已创建的资源
cleanup_on_failure() {
    kubectl delete deployment "$DEPLOYMENT_NAME" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
    kubectl delete service "$SERVICE_NAME" -n "$NAMESPACE" --ignore-not-found >/dev/null 2>&1 || true
}

# 应用资源
set +e
KUBECTL_OUTPUT=$(echo "$FULL_YAML" | kubectl apply -f - 2>&1)
KUBECTL_STATUS=$?
set -e

if [ $KUBECTL_STATUS -ne 0 ]; then
    cleanup_on_failure
    json_error "RESOURCE_APPLY_FAILED" "$ID" "Failed to apply resources" "$KUBECTL_OUTPUT"
    exit 1
fi

# 获取 Service 端口（立即返回，不等待 Deployment ready）
ACTUAL_PORT=""
if [ "$SERVICE_TYPE" = "NodePort" ]; then
    ACTUAL_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
elif [ "$SERVICE_TYPE" = "LoadBalancer" ]; then
    ACTUAL_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
else
    ACTUAL_PORT="${CONTAINER_PORT}"
fi

# 返回 pending 状态，前端通过 status 接口轮询最终状态
echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"pending\",\"port\":\"$ACTUAL_PORT\",\"detail\":\"Deployment starting (0/${REPLICAS} replicas ready)\"}"
exit 0

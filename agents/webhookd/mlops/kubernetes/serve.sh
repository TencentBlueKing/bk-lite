#!/bin/bash

# webhookd mlops serve script (Kubernetes)
# 接收 JSON: {"id": "serving-001", "mlflow_tracking_uri": "http://mlflow.default.svc.cluster.local:15000", "mlflow_model_uri": "models:/model/1", "train_image": "classify-timeseries:latest", "workers": 2, "namespace": "mlops", "port": 30000, "service_type": "NodePort", "device": "auto|cpu|gpu"}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "INVALID_JSON" "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 检查 kubectl 是否可用
if ! command -v kubectl >/dev/null 2>&1; then
    echo '{"status":"error","code":"KUBECTL_NOT_FOUND","message":"kubectl command not found"}' >&2
    exit 1
fi

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
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

# 应用资源
KUBECTL_OUTPUT=$(echo "$FULL_YAML" | kubectl apply -f - 2>&1)
KUBECTL_STATUS=$?

if [ $KUBECTL_STATUS -ne 0 ]; then
    json_error "RESOURCE_APPLY_FAILED" "$ID" "Failed to apply resources" "$KUBECTL_OUTPUT"
    exit 1
fi

# 等待 Deployment 稳定（最多等待 30 秒）
echo "[INFO] Waiting for deployment to be ready..." >&2
if kubectl wait --for=condition=available --timeout=30s deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    # 获取实际的服务端口
    ACTUAL_PORT=""
    if [ "$SERVICE_TYPE" = "NodePort" ]; then
        ACTUAL_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "")
    elif [ "$SERVICE_TYPE" = "LoadBalancer" ]; then
        ACTUAL_PORT=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    else
        ACTUAL_PORT="${CONTAINER_PORT}"
    fi
    
    # 返回成功
    echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"running\",\"port\":\"$ACTUAL_PORT\",\"detail\":\"Deployment ready with ${REPLICAS} replica(s)\"}"
    exit 0
else
    # Deployment 未能在 30 秒内就绪
    json_error "DEPLOYMENT_NOT_READY" "$ID" "Deployment created but not ready within 30 seconds. Use status.sh to check progress."
    exit 1
fi

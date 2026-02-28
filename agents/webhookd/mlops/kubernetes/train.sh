#!/bin/bash

# webhookd mlops train script (Kubernetes)
# 接收 JSON: {"id": "train-001", "bucket": "datasets", "dataset": "file.zip", "config": "config.yml", "train_image": "classify-timeseries:latest", "namespace": "mlops", "minio_endpoint": "http://minio.default.svc.cluster.local:9000", "mlflow_tracking_uri": "http://mlflow.default.svc.cluster.local:15000", "minio_access_key": "...", "minio_secret_key": "...", "device": "auto|cpu|gpu"}

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
BUCKET=$(echo "$JSON_DATA" | jq -r '.bucket // empty')
DATASET=$(echo "$JSON_DATA" | jq -r '.dataset // empty')
CONFIG=$(echo "$JSON_DATA" | jq -r '.config // empty')
MINIO_ENDPOINT=$(echo "$JSON_DATA" | jq -r '.minio_endpoint // empty')
MLFLOW_TRACKING_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_tracking_uri // empty')
MINIO_ACCESS_KEY=$(echo "$JSON_DATA" | jq -r '.minio_access_key // empty')
MINIO_SECRET_KEY=$(echo "$JSON_DATA" | jq -r '.minio_secret_key // empty')
NAMESPACE=$(echo "$JSON_DATA" | jq -r '.namespace // empty')
TRAIN_IMAGE=$(echo "$JSON_DATA" | jq -r '.train_image // empty')
DEVICE=$(echo "$JSON_DATA" | jq -r '.device // empty')

# 使用默认命名空间（如果未指定）
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="$KUBERNETES_NAMESPACE"
fi

# 验证必需参数（逐个检查以便精确定位缺失字段）
MISSING_FIELDS=""
[ -z "$ID" ] && MISSING_FIELDS="${MISSING_FIELDS}id, "
[ -z "$BUCKET" ] && MISSING_FIELDS="${MISSING_FIELDS}bucket, "
[ -z "$DATASET" ] && MISSING_FIELDS="${MISSING_FIELDS}dataset, "
[ -z "$CONFIG" ] && MISSING_FIELDS="${MISSING_FIELDS}config, "

if [ -n "$MISSING_FIELDS" ]; then
    # 移除末尾的 ", "
    MISSING_FIELDS="${MISSING_FIELDS%, }"
    json_error "MISSING_REQUIRED_FIELD" "${ID:-unknown}" "Missing required fields: ${MISSING_FIELDS}"
    exit 1
fi

if [ -z "$MINIO_ENDPOINT" ] || [ -z "$MLFLOW_TRACKING_URI" ]; then
    json_error "INVALID_ENDPOINT" "$ID" "Missing service endpoints (minio_endpoint or mlflow_tracking_uri)"
    exit 1
fi

if [ -z "$MINIO_ACCESS_KEY" ] || [ -z "$MINIO_SECRET_KEY" ]; then
    json_error "MISSING_CREDENTIALS" "$ID" "Missing MinIO credentials"
    exit 1
fi

if [ -z "$TRAIN_IMAGE" ]; then
    json_error "MISSING_TRAIN_IMAGE" "$ID" "Missing required field: train_image"
    exit 1
fi

# 将服务短名称解析为 FQDN（跨 namespace 访问时必需）
MINIO_ENDPOINT=$(resolve_endpoint_fqdn "$MINIO_ENDPOINT")
MLFLOW_TRACKING_URI=$(resolve_endpoint_fqdn "$MLFLOW_TRACKING_URI")

# Job 名称（Kubernetes 资源名称必须符合 DNS-1123 标准）
K8S_NAME=$(sanitize_k8s_name "$ID")
JOB_NAME="${K8S_NAME}"

# 确保命名空间存在
ensure_namespace "$NAMESPACE" || {
    json_error "NAMESPACE_CREATION_FAILED" "$ID" "Failed to create namespace: $NAMESPACE"
    exit 1
}

# 检查 Job 是否已存在
set +e
JOB_JSON=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o json 2>/dev/null)
set -e

if [ -n "$JOB_JSON" ]; then
    # 检查是否正在删除中（有 deletionTimestamp）
    DELETION_TS=$(echo "$JOB_JSON" | jq -r '.metadata.deletionTimestamp // empty')
    if [ -n "$DELETION_TS" ]; then
        json_error "JOB_TERMINATING" "$ID" "Training job is being deleted. Please wait and try again."
        exit 1
    fi
    
    # 检查 Job 状态
    JOB_COMPLETE=$(echo "$JOB_JSON" | jq -r '.status.conditions[]? | select(.type=="Complete") | .status // empty')
    JOB_FAILED=$(echo "$JOB_JSON" | jq -r '.status.conditions[]? | select(.type=="Failed") | .status // empty')
    ACTIVE_PODS=$(echo "$JOB_JSON" | jq -r '.status.active // 0')
    
    if [ "$ACTIVE_PODS" != "0" ] && [ "$ACTIVE_PODS" != "null" ] && [ -n "$ACTIVE_PODS" ]; then
        # Job 还在运行中
        json_error "JOB_ALREADY_RUNNING" "$ID" "Training job is still running" "Active pods: $ACTIVE_PODS. Please wait for the current training to complete or stop it first."
        exit 1
    elif [ "$JOB_COMPLETE" = "True" ]; then
        # Job 已完成
        json_error "JOB_ALREADY_EXISTS" "$ID" "Training job already completed" "Use stop.sh to delete it before starting a new training."
        exit 1
    elif [ "$JOB_FAILED" = "True" ]; then
        # Job 已失败
        json_error "JOB_ALREADY_EXISTS" "$ID" "Training job exists (failed)" "Use stop.sh to delete it before starting a new training."
        exit 1
    else
        # 其他状态（pending 等）
        json_error "JOB_ALREADY_EXISTS" "$ID" "Training job already exists" "Use stop.sh to delete it before starting a new training."
        exit 1
    fi
fi

# 创建 MinIO Secret
SECRET_NAME=$(generate_secret_name "$K8S_NAME")
create_minio_secret "$NAMESPACE" "$SECRET_NAME" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" || {
    json_error "SECRET_CREATION_FAILED" "$ID" "Failed to create MinIO secret"
    exit 1
}

# 配置设备资源
setup_device_resources "$DEVICE" || {
    json_error "DEVICE_SETUP_FAILED" "$ID" "Failed to setup device: GPU required but not available"
    exit 1
}

# 生成 Kubernetes Job YAML
JOB_YAML=$(cat <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: mlops-train
    job-id: ${ID}
spec:
  ttlSecondsAfterFinished: 300  # 5分钟后自动清理（Job + Secret 级联删除）
  backoffLimit: 0  # 不重试
  activeDeadlineSeconds: 86400  # 24小时强制终止（防止僵尸任务）
  template:
    metadata:
      labels:
        app: mlops-train
        job-id: ${ID}
    spec:
      restartPolicy: Never
      containers:
      - name: train
        image: ${TRAIN_IMAGE}
        command: ["/apps/support-files/scripts/train-model.sh"]
        args: ["${BUCKET}", "${DATASET}", "${CONFIG}"]
        env:
        - name: MINIO_ENDPOINT
          value: "${MINIO_ENDPOINT}"
        - name: MLFLOW_TRACKING_URI
          value: "${MLFLOW_TRACKING_URI}"
        - name: MINIO_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: ${SECRET_NAME}
              key: access_key
        - name: MINIO_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: ${SECRET_NAME}
              key: secret_key
EOF
)

# 添加设备资源限制（如果配置了）
if [ -n "$DEVICE_LIMIT_YAML" ]; then
    JOB_YAML=$(cat <<EOF
${JOB_YAML}
        resources:
          limits:
${DEVICE_LIMIT_YAML}
          requests:
${DEVICE_LIMIT_YAML}
EOF
)
fi

# 应用 Job
set +e
KUBECTL_OUTPUT=$(echo "$JOB_YAML" | kubectl apply -f - 2>&1)
KUBECTL_STATUS=$?
set -e

if [ $KUBECTL_STATUS -ne 0 ]; then
    json_error "JOB_APPLY_FAILED" "$ID" "Failed to apply job manifest" "$KUBECTL_OUTPUT"
    # 清理 Secret
    delete_secret "$NAMESPACE" "$SECRET_NAME"
    exit 1
fi

# 设置 Secret 的 ownerReference（Job 删除时自动清理 Secret）
JOB_UID=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o jsonpath='{.metadata.uid}' 2>/dev/null || echo "")
if [ -n "$JOB_UID" ]; then
    set_secret_owner "$NAMESPACE" "$SECRET_NAME" "Job" "$JOB_NAME" "$JOB_UID" || true
fi

# 返回 pending 状态，前端通过 status 接口轮询最终状态
echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"pending\",\"detail\":\"Training job created, waiting for pod to start\"}"
exit 0

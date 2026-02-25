#!/bin/bash

# webhookd mlops train script (Kubernetes)
# 接收 JSON: {"id": "train-001", "bucket": "datasets", "dataset": "file.zip", "config": "config.yml", "train_image": "classify-timeseries:latest", "namespace": "mlops", "minio_endpoint": "http://minio.default.svc.cluster.local:9000", "mlflow_tracking_uri": "http://mlflow.default.svc.cluster.local:15000", "minio_access_key": "...", "minio_secret_key": "...", "device": "auto|cpu|gpu"}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh" 2>&1 || {
    echo '{"status":"error","code":"COMMON_SH_LOAD_FAILED","message":"Failed to load common.sh"}' >&2
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
    echo '{"status":"error","code":"JQ_NOT_FOUND","message":"jq command not found"}' >&2
    exit 1
fi

# 检查 kubectl 是否可用
if ! command -v kubectl >/dev/null 2>&1; then
    echo '{"status":"error","code":"KUBECTL_NOT_FOUND","message":"kubectl command not found"}' >&2
    exit 1
fi

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty' 2>/dev/null) || {
    echo '{"status":"error","code":"JSON_PARSE_FAILED","message":"Failed to parse JSON data"}' >&2
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

# 验证必需参数
if [ -z "$ID" ] || [ -z "$BUCKET" ] || [ -z "$DATASET" ] || [ -z "$CONFIG" ]; then
    json_error "MISSING_REQUIRED_FIELD" "${ID:-unknown}" "Missing required fields (id, bucket, dataset, or config)"
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

# Job 名称（Kubernetes 资源名称必须符合 DNS-1123 标准）
K8S_NAME=$(sanitize_k8s_name "$ID")
JOB_NAME="${K8S_NAME}"

# 确保命名空间存在
ensure_namespace "$NAMESPACE" || {
    json_error "NAMESPACE_CREATION_FAILED" "$ID" "Failed to create namespace: $NAMESPACE"
    exit 1
}

# 检查 Job 是否已存在
if kubectl get job "$JOB_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "[INFO] Job $JOB_NAME already exists, checking status..." >&2
    
    # 检查 Job 状态
    JOB_COMPLETE=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || echo "")
    JOB_FAILED=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || echo "")
    ACTIVE_PODS=$(kubectl get job "$JOB_NAME" -n "$NAMESPACE" -o jsonpath='{.status.active}' 2>/dev/null || echo "0")
    
    if [ "$JOB_COMPLETE" = "True" ] || [ "$JOB_FAILED" = "True" ]; then
        # Job 已完成或失败，可以安全删除并重新创建
        echo "[INFO] Previous job has finished (Complete: $JOB_COMPLETE, Failed: $JOB_FAILED), deleting old job..." >&2
        kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --wait=true >/dev/null 2>&1 || {
            json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete old job"
            exit 1
        }
        echo "[INFO] Old job deleted successfully" >&2
        sleep 1
    elif [ -n "$ACTIVE_PODS" ] && [ "$ACTIVE_PODS" != "0" ]; then
        # Job 还在运行中（前端应该已经阻止，但这里做双重保护）
        json_error "JOB_ALREADY_RUNNING" "$ID" "Training job is still running" "Active pods: $ACTIVE_PODS. Please wait for the current training to complete."
        exit 1
    else
        # 未知状态或没有活跃 Pod，安全起见删除
        echo "[WARN] Job in unknown state (Complete: $JOB_COMPLETE, Failed: $JOB_FAILED, Active: $ACTIVE_PODS), deleting..." >&2
        kubectl delete job "$JOB_NAME" -n "$NAMESPACE" --wait=true >/dev/null 2>&1 || {
            json_error "JOB_DELETE_FAILED" "$ID" "Failed to delete old job"
            exit 1
        }
        echo "[INFO] Old job deleted successfully" >&2
        sleep 1
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
  ttlSecondsAfterFinished: 3600  # 1小时后自动清理
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
KUBECTL_OUTPUT=$(echo "$JOB_YAML" | kubectl apply -f - 2>&1)
KUBECTL_STATUS=$?

if [ $KUBECTL_STATUS -eq 0 ]; then
    # 等待 1 秒检查 Job 是否创建成功
    sleep 1
    if kubectl get job "$JOB_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
        json_success "$ID" "Training job created successfully" "job" "$JOB_NAME"
        exit 0
    else
        json_error "JOB_CREATION_FAILED" "$ID" "Job was not created" "$KUBECTL_OUTPUT"
        # 清理 Secret
        delete_secret "$NAMESPACE" "$SECRET_NAME"
        exit 1
    fi
else
    json_error "JOB_APPLY_FAILED" "$ID" "Failed to apply job manifest (exit code: $KUBECTL_STATUS)" "$KUBECTL_OUTPUT"
    # 清理 Secret
    delete_secret "$NAMESPACE" "$SECRET_NAME"
    exit 1
fi

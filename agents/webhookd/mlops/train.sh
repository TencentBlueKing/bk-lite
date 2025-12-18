#!/bin/bash

# webhookd mlops train script
# 接收 JSON: {"id": "train-001", "bucket": "datasets", "dataset": "file.zip", "config": "config.yml", "minio_access_key": "...", "minio_secret_key": "..."}

set -e

# 加载公共配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 解析传入的 JSON 数据（第一个参数）
if [ -z "$1" ]; then
    json_error "" "No JSON data provided"
    exit 1
fi

JSON_DATA="$1"

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
BUCKET=$(echo "$JSON_DATA" | jq -r '.bucket // empty')
DATASET=$(echo "$JSON_DATA" | jq -r '.dataset // empty')
CONFIG=$(echo "$JSON_DATA" | jq -r '.config // empty')
MINIO_ACCESS_KEY=$(echo "$JSON_DATA" | jq -r '.minio_access_key // empty')
MINIO_SECRET_KEY=$(echo "$JSON_DATA" | jq -r '.minio_secret_key // empty')

# 验证必需参数
if [ -z "$ID" ] || [ -z "$BUCKET" ] || [ -z "$DATASET" ] || [ -z "$CONFIG" ]; then
    json_error "${ID:-unknown}" "Missing required fields (id, bucket, dataset, or config)"
    exit 1
fi

if [ -z "$MINIO_ACCESS_KEY" ] || [ -z "$MINIO_SECRET_KEY" ]; then
    json_error "$ID" "Missing MinIO credentials"
    exit 1
fi

# 容器名称
CONTAINER_NAME="${ID}"

# 检查容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    json_error "$ID" "Training job already exists" "Use stop.sh to remove it first"
    exit 1
fi

# 获取服务endpoint
MINIO_ENDPOINT=$(get_minio_endpoint)
MLFLOW_TRACKING_URI=$(get_mlflow_endpoint)

# 验证endpoint是否获取成功
if [ -z "$MINIO_ENDPOINT" ] || [ -z "$MLFLOW_TRACKING_URI" ]; then
    json_error "$ID" "Failed to get Docker gateway IP"
    exit 1
fi

# 检查镜像是否存在
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${TRAIN_IMAGE}$"; then
    json_error "$ID" "Training image not found: $TRAIN_IMAGE"
    exit 1
fi

# 启动训练容器（覆盖 ENTRYPOINT，直接运行训练脚本）
DOCKER_OUTPUT=$(docker run -d --rm \
    --name "$CONTAINER_NAME" \
    --entrypoint /apps/support-files/scripts/train-model.sh \
    -e MINIO_ENDPOINT="$MINIO_ENDPOINT" \
    -e MLFLOW_TRACKING_URI="$MLFLOW_TRACKING_URI" \
    -e MINIO_ACCESS_KEY="$MINIO_ACCESS_KEY" \
    -e MINIO_SECRET_KEY="$MINIO_SECRET_KEY" \
    "$TRAIN_IMAGE" "$BUCKET" "$DATASET" "$CONFIG" 2>&1)

DOCKER_STATUS=$?

if [ $DOCKER_STATUS -eq 0 ]; then
    # 等待1秒检查容器是否真的在运行
    sleep 1
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        json_success "$ID" "Training started successfully" "container" "$CONTAINER_NAME"
        exit 0
    else
        # 容器已退出，获取日志（现在不使用--rm所以可以获取）
        CONTAINER_LOGS=$(docker logs "$CONTAINER_NAME" 2>&1)
        CONTAINER_EXIT_CODE=$(docker inspect "$CONTAINER_NAME" -f '{{.State.ExitCode}}' 2>/dev/null || echo "unknown")
        json_error "$ID" "Container exited immediately (exit code: $CONTAINER_EXIT_CODE)" "$CONTAINER_LOGS"
        exit 1
    fi
else
    json_error "$ID" "Failed to start training (exit code: $DOCKER_STATUS)" "$DOCKER_OUTPUT"
    exit 1
fi
    exit 1
fi

#!/bin/bash

# webhookd mlops serve script
# 接收 JSON: {"id": "serving-001", "mlflow_tracking_uri": "http://127.0.0.1:15000", "mlflow_model_uri": "models:/model/1", "train_image": "classify-timeseries:latest", "workers": 2, "network_mode": "bridge"}

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

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
MLFLOW_TRACKING_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_tracking_uri // empty')
MLFLOW_MODEL_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_model_uri // empty')
WORKERS=$(echo "$JSON_DATA" | jq -r '.workers // "2"')
PORT=$(echo "$JSON_DATA" | jq -r '.port // empty')
NETWORK_MODE=$(echo "$JSON_DATA" | jq -r '.network_mode // "bridge"')
TRAIN_IMAGE=$(echo "$JSON_DATA" | jq -r '.train_image // empty')

# 验证必需参数
if [ -z "$ID" ] || [ -z "$MLFLOW_TRACKING_URI" ] || [ -z "$MLFLOW_MODEL_URI" ]; then
    json_error "MISSING_REQUIRED_FIELD" "${ID:-unknown}" "Missing required fields (id, mlflow_tracking_uri, mlflow_model_uri)"
    exit 1
fi

if [ -z "$TRAIN_IMAGE" ]; then
    json_error "MISSING_TRAIN_IMAGE" "$ID" "Missing required field: train_image"
    exit 1
fi

# 检查容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^${ID}$"; then
    json_error "CONTAINER_ALREADY_EXISTS" "$ID" "Container already exists. Use remove.sh to delete it first."
    exit 1
fi

# 用户指定端口时检查是否被占用
if [ -n "$PORT" ]; then
    if ss -tln 2>/dev/null | grep -E ":(${PORT})[^0-9]" | grep -q "LISTEN"; then
        json_error "PORT_IN_USE" "$ID" "Port $PORT is already in use. Please choose a different port."
        exit 1
    fi
fi

# 检查镜像是否存在
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${TRAIN_IMAGE}$"; then
    json_error "IMAGE_NOT_FOUND" "$ID" "Serving image not found: $TRAIN_IMAGE"
    exit 1
fi

# 容器内固定端口 3000
CONTAINER_PORT="3000"

# 构建端口映射参数
if [ -n "$PORT" ]; then
    # 用户指定端口：映射到指定端口
    PORT_MAPPING="${PORT}:${CONTAINER_PORT}"
else
    # Docker 自动分配：只指定容器端口，宿主机端口由 Docker 随机分配
    PORT_MAPPING="${CONTAINER_PORT}"
fi

# 启动 serving 容器（使用传入的网络模式）
DOCKER_OUTPUT=$(docker run -d \
    --name "$ID" \
    --network "$NETWORK_MODE" \
    -p "${PORT_MAPPING}" \
    --restart unless-stopped \
    --log-driver json-file \
    --log-opt max-size=100m \
    --log-opt max-file=3 \
    -e BENTOML_HOST="0.0.0.0" \
    -e BENTOML_PORT="$CONTAINER_PORT" \
    -e MODEL_SOURCE="mlflow" \
    -e MLFLOW_TRACKING_URI="$MLFLOW_TRACKING_URI" \
    -e MLFLOW_MODEL_URI="$MLFLOW_MODEL_URI" \
    -e WORKERS="$WORKERS" \
    -e ALLOW_DUMMY_FALLBACK="false" \
    --entrypoint "uv" \
    "$TRAIN_IMAGE" \
    run bentoml serve classify_timeseries_server.serving.service:MLService 2>&1)

DOCKER_STATUS=$?

if [ $DOCKER_STATUS -ne 0 ]; then
    json_error "CONTAINER_START_FAILED" "$ID" "Failed to start container" "$DOCKER_OUTPUT"
    exit 1
fi

# 等待容器稳定（5秒）
sleep 5

# 检查容器是否还在运行
if ! docker ps -q -f name="^${ID}$" | grep -q .; then
    # 容器已退出，获取退出状态
    EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' "$ID" 2>/dev/null || echo "unknown")
    json_error "CONTAINER_EXITED" "$ID" "Container exited with code $EXIT_CODE. Use logs.sh to view logs and remove.sh to cleanup."
    exit 1
fi

# 获取实际分配的宿主机端口（Docker 自动分配时需要）
if [ -z "$PORT" ]; then
    PORT=$(docker inspect "$ID" -f '{{(index (index .NetworkSettings.Ports "3000/tcp") 0).HostPort}}' 2>/dev/null || echo "")
fi

# 返回成功（格式与 status.sh 一致）
echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"running\",\"port\":\"$PORT\",\"detail\":\"Up\"}"
exit 0

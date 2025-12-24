#!/bin/bash

# webhookd mlops serve script
# 接收 JSON: {"id": "serving-001", "mlflow_tracking_uri": "http://127.0.0.1:15000", "mlflow_model_uri": "models:/model/1", "workers": 2}

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
MLFLOW_TRACKING_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_tracking_uri // empty')
MLFLOW_MODEL_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_model_uri // empty')
WORKERS=$(echo "$JSON_DATA" | jq -r '.workers // "2"')

# 验证必需参数
if [ -z "$ID" ] || [ -z "$MLFLOW_TRACKING_URI" ] || [ -z "$MLFLOW_MODEL_URI" ]; then
    json_error "${ID:-unknown}" "Missing required fields (id, mlflow_tracking_uri, mlflow_model_uri)"
    exit 1
fi

# 检查容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^${ID}$"; then
    json_error "$ID" "Container already exists. Use remove.sh to delete it first."
    exit 1
fi

# 查找可用端口（3001-3100 范围，跳过 3000 以测试 .env 覆盖问题）
find_available_port() {
    for port in $(seq 3001 3100); do
        # 检查 WSL/Linux 内的端口占用
        if ss -tln 2>/dev/null | grep -E ":(${port})[^0-9]" | grep -q "LISTEN"; then
            continue
        fi
        
        # 端口未占用，返回该端口
        echo $port
        return 0
    done
    
    return 1
}

PORT=$(find_available_port)
if [ -z "$PORT" ]; then
    json_error "$ID" "All ports (3000-3100) are in use. Please stop some services first."
    exit 1
fi

# 检查镜像是否存在
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^${TRAIN_IMAGE}$"; then
    json_error "$ID" "Serving image not found: $TRAIN_IMAGE"
    exit 1
fi

# 启动 serving 容器
DOCKER_OUTPUT=$(docker run -d \
    --name "$ID" \
    --network host \
    --restart unless-stopped \
    --log-driver json-file \
    --log-opt max-size=100m \
    --log-opt max-file=3 \
    -e BENTOML_HOST="0.0.0.0" \
    -e BENTOML_PORT="$PORT" \
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
    json_error "$ID" "Failed to start container" "$DOCKER_OUTPUT"
    exit 1
fi

# 等待容器稳定（5秒）
sleep 5

# 检查容器是否还在运行
if ! docker ps -q -f name="^${ID}$" | grep -q .; then
    # 容器已退出，获取退出状态
    EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' "$ID" 2>/dev/null || echo "unknown")
    json_error "$ID" "Container exited with code $EXIT_CODE. Use logs.sh to view logs and remove.sh to cleanup."
    exit 1
fi

# 返回成功（格式与 status.sh 一致）
echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"running\",\"port\":\"$PORT\",\"detail\":\"Up\"}"
exit 0

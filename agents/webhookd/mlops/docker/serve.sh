#!/bin/bash

# webhookd mlops serve script
# 接收 JSON: {"id": "serving-001", "mlflow_tracking_uri": "http://127.0.0.1:15000", "mlflow_model_uri": "models:/model/1", "train_image": "classify-timeseries:latest", "workers": 2, "network_mode": "bridge", "device": "auto|cpu|gpu", "startup_timeout_seconds": 120, "timeseries_predict_timeout_seconds": 120}

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

# 模型加载可能需要访问 MLflow。初次启动必须在超时内通过 BentoML
# readiness，随后才启用容器自动重启，避免加载失败被重启环掩盖。
STARTUP_TIMEOUT_SECONDS=$(echo "$JSON_DATA" | jq -r '.startup_timeout_seconds // empty')
STARTUP_TIMEOUT_SECONDS="${STARTUP_TIMEOUT_SECONDS:-${SERVING_STARTUP_TIMEOUT_SECONDS:-120}}"
if ! [[ "$STARTUP_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || [ "$STARTUP_TIMEOUT_SECONDS" -gt 290 ]; then
    json_error "INVALID_STARTUP_TIMEOUT" "" "startup_timeout_seconds must be an integer between 1 and 290"
    exit 1
fi

# 提取必需参数
ID=$(echo "$JSON_DATA" | jq -r '.id // empty')
MLFLOW_TRACKING_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_tracking_uri // empty')
MLFLOW_MODEL_URI=$(echo "$JSON_DATA" | jq -r '.mlflow_model_uri // empty')
WORKERS=$(echo "$JSON_DATA" | jq -r '.workers // "2"')
PORT=$(echo "$JSON_DATA" | jq -r '.port // empty')
NETWORK_MODE=$(echo "$JSON_DATA" | jq -r '.network_mode // "bridge"')
TRAIN_IMAGE=$(echo "$JSON_DATA" | jq -r '.train_image // empty')
DEVICE=$(echo "$JSON_DATA" | jq -r '.device // empty')  # 未传递时为空字符串
TIMESERIES_PREDICT_TIMEOUT_SECONDS=$(echo "$JSON_DATA" | jq -r '.timeseries_predict_timeout_seconds // empty')

# 验证必需参数
if [ -z "$ID" ] || [ -z "$MLFLOW_TRACKING_URI" ] || [ -z "$MLFLOW_MODEL_URI" ]; then
    json_error "MISSING_REQUIRED_FIELD" "${ID:-unknown}" "Missing required fields (id, mlflow_tracking_uri, mlflow_model_uri)"
    exit 1
fi

if [ -z "$TRAIN_IMAGE" ]; then
    json_error "MISSING_TRAIN_IMAGE" "$ID" "Missing required field: train_image"
    exit 1
fi

if [ -n "$TIMESERIES_PREDICT_TIMEOUT_SECONDS" ]; then
    if ! [[ "$TIMESERIES_PREDICT_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || [ "$TIMESERIES_PREDICT_TIMEOUT_SECONDS" -gt 290 ]; then
        json_error "INVALID_PREDICT_TIMEOUT" "$ID" "timeseries_predict_timeout_seconds must be between 1 and 290"
        exit 1
    fi
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

# 配置设备参数
setup_device_args "$DEVICE" || {
    json_error "DEVICE_SETUP_FAILED" "$ID" "Failed to setup device"
    exit 1
}

# 只有时序预测调用方传入该预算，其他算法服务保持现有环境不变。
PREDICT_TIMEOUT_ENV_ARGS=()
if [ -n "$TIMESERIES_PREDICT_TIMEOUT_SECONDS" ]; then
    PREDICT_TIMEOUT_ENV_ARGS=(-e "TIMESERIES_PREDICT_TIMEOUT_SECONDS=$TIMESERIES_PREDICT_TIMEOUT_SECONDS")
fi

# 初次启动禁用重启策略；readiness 通过后再恢复 unless-stopped。
# 否则 BentoML 因模型加载失败退出时，Docker 重启环会让 docker ps 持续可见，
# 从而把失败发布误报为 running。
CID_FILE=$(mktemp)
rm -f "$CID_FILE"
trap 'rm -f "$CID_FILE"' EXIT

set +e
DOCKER_OUTPUT=$(docker run -d \
    --name "$ID" \
    --cidfile "$CID_FILE" \
    --network "$NETWORK_MODE" \
    -p "${PORT_MAPPING}" \
    $DEVICE_ARGS \
    --restart no \
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
    "${PREDICT_TIMEOUT_ENV_ARGS[@]}" \
    "$TRAIN_IMAGE" 2>&1)

DOCKER_STATUS=$?
set -e
CREATED_CONTAINER_ID=$(cat "$CID_FILE" 2>/dev/null || true)

rollback_failed_startup() {
    local original_code="$1"
    local original_message="$2"
    local container_logs=""

    if [ -z "$CREATED_CONTAINER_ID" ]; then
        json_error "$original_code" "$ID" "$original_message"
        exit 1
    fi

    # 先保留有限原始日志，再按本次 docker run 写入 cidfile 的精确 ID 回滚，
    # 避免误删同名存量容器或留下阻塞重试的半成品。
    container_logs=$(docker logs --tail 50 "$CREATED_CONTAINER_ID" 2>&1 || true)
    if ! docker rm -f "$CREATED_CONTAINER_ID" >/dev/null 2>&1; then
        json_error \
            "CONTAINER_ROLLBACK_FAILED" \
            "$ID" \
            "$original_message; failed to rollback container $CREATED_CONTAINER_ID" \
            "$container_logs"
        exit 1
    fi

    json_error "$original_code" "$ID" "$original_message" "$container_logs"
    exit 1
}

if [ $DOCKER_STATUS -ne 0 ]; then
    if [ -n "$CREATED_CONTAINER_ID" ]; then
        rollback_failed_startup \
            "CONTAINER_START_FAILED" \
            "Failed to start container: $DOCKER_OUTPUT"
    fi
    json_error "CONTAINER_START_FAILED" "$ID" "Failed to start container" "$DOCKER_OUTPUT"
    exit 1
fi

# 进程可能在端口映射可查询前就因模型加载失败退出，先保留真实退出原因。
INITIAL_STATE=$(docker inspect -f '{{.State.Status}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
if [ "$INITIAL_STATE" = "exited" ] || [ "$INITIAL_STATE" = "dead" ]; then
    EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
    rollback_failed_startup \
        "CONTAINER_EXITED" \
        "Container exited with code $EXIT_CODE before readiness and was rolled back"
fi

# 获取实际分配的宿主机端口（readiness 探测需要）
if [ "$NETWORK_MODE" = "host" ]; then
    PORT="$CONTAINER_PORT"
elif [ -z "$PORT" ]; then
    PORT=$(docker inspect "$CREATED_CONTAINER_ID" -f '{{(index (index .NetworkSettings.Ports "3000/tcp") 0).HostPort}}' 2>/dev/null || echo "")
fi

if [ -z "$PORT" ]; then
    rollback_failed_startup \
        "PORT_ALLOCATION_FAILED" \
        "Failed to resolve serving port; container was rolled back"
fi

# 必须等模型加载完成且 BentoML readiness 成功，不能只看容器进程存在。
READY_URL="http://127.0.0.1:${PORT}/readyz"
ELAPSED_SECONDS=0
LAST_STATE="unknown"

while [ "$ELAPSED_SECONDS" -lt "$STARTUP_TIMEOUT_SECONDS" ]; do
    LAST_STATE=$(docker inspect -f '{{.State.Status}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")

    if [ "$LAST_STATE" = "exited" ] || [ "$LAST_STATE" = "dead" ]; then
        EXIT_CODE=$(docker inspect -f '{{.State.ExitCode}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
        rollback_failed_startup \
            "CONTAINER_EXITED" \
            "Container exited with code $EXIT_CODE before readiness and was rolled back"
    fi

    if [ "$LAST_STATE" = "running" ] && curl --fail --silent --show-error --max-time 2 "$READY_URL" >/dev/null 2>&1; then
        if ! docker update --restart unless-stopped "$CREATED_CONTAINER_ID" >/dev/null 2>&1; then
            rollback_failed_startup \
                "RESTART_POLICY_UPDATE_FAILED" \
                "Serving became ready but restart policy update failed; container was rolled back"
        fi

        echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"running\",\"port\":\"$PORT\",\"detail\":\"Ready\"}"
        exit 0
    fi

    sleep 1
    ELAPSED_SECONDS=$((ELAPSED_SECONDS + 1))
done

rollback_failed_startup \
    "CONTAINER_NOT_READY" \
    "Serving did not become ready within ${STARTUP_TIMEOUT_SECONDS} seconds (container state: ${LAST_STATE}); container was rolled back"

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
SERVING_INSTANCE_ID=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
export SERVING_INSTANCE_ID

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

# startup_timeout_seconds 是从请求进入脚本到 readiness 完成的总预算；
# webhookd 另外预留 5 秒用于有界回滚，因此这里把单次回滚限制为 4 秒。
ROLLBACK_TIMEOUT_SECONDS="${SERVING_ROLLBACK_TIMEOUT_SECONDS:-4}"
if ! [[ "$ROLLBACK_TIMEOUT_SECONDS" =~ ^[1-4]$ ]]; then
    json_error "INVALID_ROLLBACK_TIMEOUT" "$ID" "SERVING_ROLLBACK_TIMEOUT_SECONDS must be between 1 and 4"
    exit 1
fi
STARTUP_DEADLINE=$((SECONDS + STARTUP_TIMEOUT_SECONDS))
ROLLBACK_DEADLINE=0

run_bounded() {
    local timeout_seconds="$1"
    shift
    python3 "$SCRIPT_DIR/run_bounded.py" "$timeout_seconds" "$@"
}

remaining_startup_seconds() {
    local remaining=$((STARTUP_DEADLINE - SECONDS))
    if [ "$remaining" -lt 0 ]; then
        remaining=0
    fi
    echo "$remaining"
}

run_with_startup_budget() {
    local remaining
    remaining=$(remaining_startup_seconds)
    if [ "$remaining" -le 0 ]; then
        return 124
    fi
    run_bounded "$remaining" "$@"
}

run_with_rollback_budget() {
    if [ "$ROLLBACK_DEADLINE" -eq 0 ]; then
        ROLLBACK_DEADLINE=$((SECONDS + ROLLBACK_TIMEOUT_SECONDS))
    fi
    local remaining=$((ROLLBACK_DEADLINE - SECONDS))
    if [ "$remaining" -le 0 ]; then
        return 124
    fi
    run_bounded "$remaining" "$@"
}

# 检查容器是否已存在；Docker 查询也属于同一个启动预算。
set +e
EXISTING_CONTAINERS=$(run_with_startup_budget docker ps -a --format '{{.Names}}' 2>&1)
DOCKER_CHECK_STATUS=$?
set -e
if [ "$DOCKER_CHECK_STATUS" -ne 0 ]; then
    json_error "DOCKER_CHECK_FAILED" "$ID" "Failed to inspect existing containers within startup budget" "$EXISTING_CONTAINERS"
    exit 1
fi
if echo "$EXISTING_CONTAINERS" | grep -q "^${ID}$"; then
    json_error "CONTAINER_ALREADY_EXISTS" "$ID" "Container already exists. Use remove.sh to delete it first."
    exit 1
fi

# 用户指定端口时用 Python 做真实 bind 检查；最终 readiness 仍会校验本次
# 启动的随机实例标识，因此 bind 与容器启动间的竞争不会被误报为成功。
if [ -n "$PORT" ]; then
    if ! run_with_startup_budget python3 -c \
        'import socket, sys; s=socket.socket(); s.bind(("0.0.0.0", int(sys.argv[1]))); s.close()' \
        "$PORT" >/dev/null 2>&1; then
        json_error "PORT_IN_USE" "$ID" "Port $PORT is already in use. Please choose a different port."
        exit 1
    fi
fi

# 检查镜像是否存在
if ! run_with_startup_budget docker image inspect "$TRAIN_IMAGE" >/dev/null 2>&1; then
    json_error "IMAGE_NOT_FOUND" "$ID" "Serving image not found: $TRAIN_IMAGE"
    exit 1
fi

# bridge 模式继续使用容器端口 3000；host 模式必须使用本次启动独占的
# 宿主端口，避免 readiness 命中宿主上另一个服务。
CONTAINER_PORT="3000"
PORT_ARGS=()

# 构建端口映射参数。host 网络不接受 -p，BentoML 直接监听独占宿主端口。
if [ "$NETWORK_MODE" = "host" ]; then
    if [ -z "$PORT" ]; then
        PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
    fi
    CONTAINER_PORT="$PORT"
elif [ -n "$PORT" ]; then
    PORT_ARGS=(-p "${PORT}:${CONTAINER_PORT}")
else
    PORT_ARGS=(-p "${CONTAINER_PORT}")
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
CREATED_CONTAINER_ID=""
STARTUP_COMMITTED="false"
ROLLBACK_IN_PROGRESS="false"

cleanup_on_exit() {
    local status=$?
    if [ -z "$CREATED_CONTAINER_ID" ] && [ -f "$CID_FILE" ]; then
        CREATED_CONTAINER_ID=$(cat "$CID_FILE" 2>/dev/null || true)
    fi
    rm -f "$CID_FILE"
    if [ "$status" -ne 0 ] \
        && [ "$STARTUP_COMMITTED" != "true" ] \
        && [ "$ROLLBACK_IN_PROGRESS" != "true" ] \
        && [ -n "$CREATED_CONTAINER_ID" ]; then
        run_with_rollback_budget docker rm -f "$CREATED_CONTAINER_ID" >/dev/null 2>&1 || true
    fi
}

trap cleanup_on_exit EXIT
trap 'exit 143' TERM INT HUP

set +e
DOCKER_OUTPUT=$(run_with_startup_budget docker run -d \
    --name "$ID" \
    --cidfile "$CID_FILE" \
    --label "bk-lite.startup-id=$SERVING_INSTANCE_ID" \
    --network "$NETWORK_MODE" \
    "${PORT_ARGS[@]}" \
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
    -e BENTOML_CONTAINERIZED="true" \
    -e SERVING_INSTANCE_ID="$SERVING_INSTANCE_ID" \
    "${PREDICT_TIMEOUT_ENV_ARGS[@]}" \
    "$TRAIN_IMAGE" 2>&1)

DOCKER_STATUS=$?
set -e
CREATED_CONTAINER_ID=$(cat "$CID_FILE" 2>/dev/null || true)
if [ -z "$CREATED_CONTAINER_ID" ]; then
    ROLLBACK_DEADLINE=$((SECONDS + ROLLBACK_TIMEOUT_SECONDS))
    CREATED_CONTAINER_ID=$(run_with_rollback_budget docker ps -aq \
        --filter "label=bk-lite.startup-id=$SERVING_INSTANCE_ID" \
        --no-trunc 2>/dev/null | head -n 1 || true)
fi
if [ "$DOCKER_STATUS" -eq 0 ]; then
    ROLLBACK_DEADLINE=0
fi

rollback_failed_startup() {
    local original_code="$1"
    local original_message="$2"
    local container_logs=""
    local log_timeout_seconds=0
    local rollback_status=0

    if [ -z "$CREATED_CONTAINER_ID" ]; then
        json_error "$original_code" "$ID" "$original_message"
        exit 1
    fi

    # 先保留有限原始日志，再按本次 docker run 写入 cidfile 的精确 ID 回滚，
    # 避免误删同名存量容器或留下阻塞重试的半成品。
    ROLLBACK_IN_PROGRESS="true"
    if [ "$ROLLBACK_DEADLINE" -eq 0 ]; then
        ROLLBACK_DEADLINE=$((SECONDS + ROLLBACK_TIMEOUT_SECONDS))
    fi
    # 日志最多占 1 秒，优先把共享回滚预算留给 docker rm。
    log_timeout_seconds=$((ROLLBACK_DEADLINE - SECONDS))
    if [ "$log_timeout_seconds" -gt 1 ]; then
        log_timeout_seconds=1
    fi
    if [ "$log_timeout_seconds" -gt 0 ]; then
        container_logs=$(run_bounded "$log_timeout_seconds" docker logs --tail 50 "$CREATED_CONTAINER_ID" 2>&1 || true)
    fi
    set +e
    run_with_rollback_budget docker rm -f "$CREATED_CONTAINER_ID" >/dev/null 2>&1
    rollback_status=$?
    set -e
    if [ "$rollback_status" -ne 0 ]; then
        ROLLBACK_IN_PROGRESS="false"
        json_error \
            "CONTAINER_ROLLBACK_FAILED" \
            "$ID" \
            "$original_message; failed to rollback container $CREATED_CONTAINER_ID" \
            "$container_logs"
        exit 1
    fi

    CREATED_CONTAINER_ID=""
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
INITIAL_STATE=$(run_with_startup_budget docker inspect -f '{{.State.Status}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
if [ "$INITIAL_STATE" = "exited" ] || [ "$INITIAL_STATE" = "dead" ]; then
    EXIT_CODE=$(run_with_startup_budget docker inspect -f '{{.State.ExitCode}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
    rollback_failed_startup \
        "CONTAINER_EXITED" \
        "Container exited with code $EXIT_CODE before readiness and was rolled back"
fi

# 获取 bridge 模式下 Docker 自动分配的宿主机端口。
if [ "$NETWORK_MODE" != "host" ] && [ -z "$PORT" ]; then
    PORT=$(run_with_startup_budget docker inspect "$CREATED_CONTAINER_ID" -f '{{(index (index .NetworkSettings.Ports "3000/tcp") 0).HostPort}}' 2>/dev/null || echo "")
fi

if [ -z "$PORT" ]; then
    rollback_failed_startup \
        "PORT_ALLOCATION_FAILED" \
        "Failed to resolve serving port; container was rolled back"
fi

# 必须等模型加载完成，并由业务 health API 回显本次随机实例标识。
# 这会把响应绑定到本次容器，即使 host 端口在启动竞争中被其他服务抢占，
# 也不会把无关服务的 /readyz 误认成本次模型服务。
HEALTH_URL="http://127.0.0.1:${PORT}/health"
LAST_STATE="unknown"

while [ "$SECONDS" -lt "$STARTUP_DEADLINE" ]; do
    LAST_STATE=$(run_with_startup_budget docker inspect -f '{{.State.Status}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")

    if [ "$LAST_STATE" = "exited" ] || [ "$LAST_STATE" = "dead" ]; then
        EXIT_CODE=$(run_with_startup_budget docker inspect -f '{{.State.ExitCode}}' "$CREATED_CONTAINER_ID" 2>/dev/null || echo "unknown")
        rollback_failed_startup \
            "CONTAINER_EXITED" \
            "Container exited with code $EXIT_CODE before readiness and was rolled back"
    fi

    REMAINING_SECONDS=$((STARTUP_DEADLINE - SECONDS))
    CURL_TIMEOUT_SECONDS=2
    if [ "$REMAINING_SECONDS" -lt "$CURL_TIMEOUT_SECONDS" ]; then
        CURL_TIMEOUT_SECONDS="$REMAINING_SECONDS"
    fi

    HEALTH_RESPONSE=""
    if [ "$LAST_STATE" = "running" ]; then
        HEALTH_RESPONSE=$(curl --fail --silent --show-error \
            --max-time "$CURL_TIMEOUT_SECONDS" \
            --request POST \
            --header "Content-Type: application/json" \
            --data '{}' \
            "$HEALTH_URL" 2>/dev/null || true)
    fi

    if echo "$HEALTH_RESPONSE" | jq -e \
        --arg instance_id "$SERVING_INSTANCE_ID" \
        '.status == "healthy" and .startup_instance_id == $instance_id' >/dev/null 2>&1; then
        if ! run_with_startup_budget docker update --restart unless-stopped "$CREATED_CONTAINER_ID" >/dev/null 2>&1; then
            rollback_failed_startup \
                "RESTART_POLICY_UPDATE_FAILED" \
                "Serving became ready but restart policy update failed; container was rolled back"
        fi

        STARTUP_COMMITTED="true"
        echo "{\"status\":\"success\",\"id\":\"$ID\",\"state\":\"running\",\"port\":\"$PORT\",\"detail\":\"Ready\"}"
        exit 0
    fi

    if [ "$SECONDS" -lt "$STARTUP_DEADLINE" ]; then
        sleep 1
    fi
done

rollback_failed_startup \
    "CONTAINER_NOT_READY" \
    "Serving did not become ready within ${STARTUP_TIMEOUT_SECONDS} seconds (container state: ${LAST_STATE}); container was rolled back"

#!/bin/bash
set -euo pipefail
# ANSI escape codes for colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages with colored output
log() {
    local level="$1"
    local message="$2"
    local color=""

    case "$level" in
        "INFO")
            color="$BLUE"
            ;;
        "WARNING")
            color="$YELLOW"
            ;;
        "ERROR")
            color="$RED"
            ;;
        "SUCCESS")
            color="$GREEN"
            ;;
        *)
            color="$NC"
            ;;
    esac

    echo -e "${color}[$(date +'%Y-%m-%d %H:%M:%S')] [$level] $message${NC}"
}

DOCKER_COMPOSE_CMD=""

if command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
    log "INFO" "检测到 docker-compose 命令，使用 docker-compose 进行部署"
# 当docker compose version 返回0时，表示安装了docker compose v2
elif docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
    log "INFO" "检测到 docker compose 命令，使用 docker compose 进行部署"
else
    log "ERROR" "未找到 docker-compose 或 docker compose 命令，请安装 docker-compose或将docker升级到最新版本"
    exit 1
fi

# 检查是否添加--opspilot参数
if [[ "$@" == *"--opspilot"* ]]; then
    export OPSPILOT_ENABLED=true
    log "INFO" "检测到 --opspilot 参数，启用 OpsPilot 功能"
else
    export OPSPILOT_ENABLED=false
    log "INFO" "未检测到 --opspilot 参数，禁用 OpsPilot 功能"
fi

INSTALL_APPS="system_mgmt,cmdb,monitor,node_mgmt,console_mgmt,alerts,log,mlops,operation_analysis"

if [[ $OPSPILOT_ENABLED == "true" ]]; then
    export INSTALL_APPS="${INSTALL_APPS},opspilot"
    log "INFO" "启用 OpsPilot 功能，安装应用列表: ${INSTALL_APPS}"
    # 使用 compose/ops_pilot.yaml 文件
    export COMPOSE_CMD="${DOCKER_COMPOSE_CMD} -f compose/infra.yaml -f compose/monitor.yaml -f compose/server.yaml -f compose/web.yaml -f compose/ops_pilot.yaml -f compose/log.yaml config --no-interpolate"
else
    log "INFO" "禁用 OpsPilot 功能，安装应用列表: ${INSTALL_APPS}"
    export COMPOSE_CMD="${DOCKER_COMPOSE_CMD} -f compose/infra.yaml -f compose/monitor.yaml -f compose/server.yaml -f compose/web.yaml -f compose/log.yaml config --no-interpolate"
fi

# Function to validate environment variables
validate_env_var() {
    local var_name="$1"
    if [ -z "${!var_name}" ]; then
        log "ERROR" "Environment variable $var_name is not set."
        exit 1
    fi
}

# Function to add mirror prefix to docker image if MIRROR is set
add_mirror_prefix() {
    local image="$1"
    if [ -n "$MIRROR" ]; then
        # 如果镜像名包含斜杠，说明有仓库前缀
        if [[ "$image" == *"/"* ]]; then
            echo "${MIRROR}/${image}"
        else
            # 如果没有斜杠，说明是官方镜像，需要加上library前缀
            echo "${MIRROR}/library/${image}"
        fi
    else
        echo "$image"
    fi
}

# 生成随机密码 - 进一步优化，完全避免任何可能在YAML中引起问题的特殊字符
generate_password() {
    local length=$1
    # 只使用字母和数字，避免任何特殊字符，确保在YAML文件中不会出现解析问题
    cat /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c $length
}

# 等待容器健康状态函数
wait_container_health() {
    local container_name="$1"
    local service_name="$2"
    log "INFO" "等待 $service_name 启动..."
    until [ "$($DOCKER_COMPOSE_CMD ps $container_name --format "{{.Health}}" 2>/dev/null)" == "healthy" ]; do
        log "INFO" "等待 $service_name 启动..."
        sleep 5
    done
    log "SUCCESS" "$service_name 已成功启动"
}

# 检查容器是否响应 HTTP 请求
check_http_response() {
    local url="$1"
    local expected_code="$2"
    local service_name="$3"
    local max_attempts="$4"
    local attempt=0

    log "INFO" "正在检查 $service_name 是否可访问..."
    
    while [ $attempt -lt $max_attempts ]; do
        response_code=$(curl -s -o /dev/null -w "%{http_code}" $url)
        if [ "$response_code" == "$expected_code" ]; then
            log "SUCCESS" "$service_name 已成功启动并可访问"
            return 0
        else
            log "INFO" "$service_name 尚未完全启动，第 $((attempt + 1)) 次尝试，等待 5 秒后继续检查..."
            sleep 5
        fi
        attempt=$((attempt + 1))
    done

    log "ERROR" "经过 $max_attempts 次尝试，$service_name 仍未成功启动"
    return 1
}

if [ -f port.env ]; then
    log "SUCCESS" "port.env文件已存在，跳过文件生成步骤..."
    source port.env
else
        # 获取本地的第一个ip为默认ip
    # Get IP address - compatible with both Linux and macOS
    if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then
        DEFAULT_IP=$(hostname -I | awk '{print $1}')
    elif command -v ifconfig >/dev/null 2>&1; then
        DEFAULT_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
    else
        DEFAULT_IP="127.0.0.1"
    fi

    # 从命令行读取HOST_IP环境变量
    read -p "输入对外访问的IP地址，默认为 [$DEFAULT_IP] " HOST_IP  < /dev/tty
    export HOST_IP=${HOST_IP:-$DEFAULT_IP}

    DEFAULT_TRAEFIK_WEB_PORT=80
    read -p "输入访问端口，默认为 [$DEFAULT_TRAEFIK_WEB_PORT] " TRAEFIK_WEB_PORT  < /dev/tty
    export TRAEFIK_WEB_PORT=${TRAEFIK_WEB_PORT:-$DEFAULT_TRAEFIK_WEB_PORT}

    # 将输入的配置写入port.env
    cat > port.env <<EOF
HOST_IP=${HOST_IP}
TRAEFIK_WEB_PORT=${TRAEFIK_WEB_PORT}
EOF
fi

# 检查common.env文件是否存在，存在则加载，不存在则生成
# 检查并设置MIRROR环境变量
MIRROR=${MIRROR:-""}
COMMON_ENV_FILE="common.env"
if [ -f "$COMMON_ENV_FILE" ]; then
    log "SUCCESS" "发现 $COMMON_ENV_FILE 配置文件，加载已保存的环境变量..."
    source $COMMON_ENV_FILE
else
    log "INFO" "未发现 $COMMON_ENV_FILE 配置文件，生成随机环境变量..."
    # 生成随机密码
    export POSTGRES_PASSWORD=$(generate_password 32)
    export REDIS_PASSWORD=$(generate_password 32)
    export SECRET_KEY=$(generate_password 32)
    export NEXTAUTH_SECRET=$(generate_password 12)
    export SIDECAR_INIT_TOKEN=$(generate_password 64)
    export NATS_ADMIN_USERNAME=admin
    export NATS_ADMIN_PASSWORD=$(generate_password 32)
    export NATS_MONITOR_USERNAME=monitor
    export NATS_MONITOR_PASSWORD=$(generate_password 32)
    export MINIO_ROOT_USER=minio
    export MINIO_ROOT_PASSWORD=$(generate_password 32)
    export RABBITMQ_DEFAULT_USER=rabbit
    export RABBITMQ_DEFAULT_PASSWORD=$(generate_password 32)
    export FALKORDB_PASSWORD=$(generate_password 32)
    export MIRROR=${MIRROR:-""}

    # 保存到common.env文件
    cat > $COMMON_ENV_FILE <<EOF
# 自动生成的环境变量配置，用于确保脚本幂等性
# 生成日期: $(date +'%Y-%m-%d %H:%M:%S')
export POSTGRES_PASSWORD=$POSTGRES_PASSWORD
export REDIS_PASSWORD=$REDIS_PASSWORD
export SECRET_KEY=$SECRET_KEY
export NEXTAUTH_SECRET=$NEXTAUTH_SECRET
export SIDECAR_INIT_TOKEN=$SIDECAR_INIT_TOKEN
export NATS_ADMIN_USERNAME=$NATS_ADMIN_USERNAME
export NATS_ADMIN_PASSWORD=$NATS_ADMIN_PASSWORD
export NATS_MONITOR_USERNAME=$NATS_MONITOR_USERNAME
export NATS_MONITOR_PASSWORD=$NATS_MONITOR_PASSWORD
export MINIO_ROOT_USER=$MINIO_ROOT_USER
export MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
export RABBITMQ_DEFAULT_USER=$RABBITMQ_DEFAULT_USER
export RABBITMQ_DEFAULT_PASSWORD=$RABBITMQ_DEFAULT_PASSWORD
export FALKORDB_PASSWORD=$FALKORDB_PASSWORD
export MIRROR=$MIRROR
EOF
    log "SUCCESS" "环境变量已生成并保存到 $COMMON_ENV_FILE 文件"
fi

if [ -n "$MIRROR" ]; then
    log "INFO" "检测到镜像仓库 MIRROR=${MIRROR}，所有 Docker 镜像将使用此镜像仓库"
else
    log "INFO" "未设置 MIRROR 环境变量，使用默认镜像仓库"
fi

# 固定的环境变量
DOCKER_IMAGE_TRAEFIK=$(add_mirror_prefix "traefik:3.3.3")
DOCKER_IMAGE_REDIS=$(add_mirror_prefix "redis:5.0.14")
DOCKER_IMAGE_NATS=$(add_mirror_prefix "nats:2.10.25")
DOCKER_IMAGE_NATS_CLI=$(add_mirror_prefix "bitnami/natscli:0.1.6")
DOCKER_IMAGE_VICTORIA_METRICS=$(add_mirror_prefix "victoriametrics/victoria-metrics:v1.106.1")
DOCKER_IMAGE_POSTGRES=$(add_mirror_prefix "postgres:15")
DOCKER_IMAGE_SERVER=$(add_mirror_prefix "bklite/server")
DOCKER_IMAGE_WEB=$(add_mirror_prefix "bklite/web")
DOCKER_NETWORK=prod
DIST_ARCH=amd64
POSTGRES_USERNAME=postgres
TRAEFIK_ENABLE_DASHBOARD=false
DEFAULT_REQUEST_TIMEOUT=10
DOCKER_IMAGE_STARGAZER=$(add_mirror_prefix "bklite/stargazer")
DOCKER_IMAGE_MINIO=$(add_mirror_prefix "minio/minio:RELEASE.2024-05-01T01-11-10Z-cpuv1")
DOCKER_IMAGE_RABBITMQ=$(add_mirror_prefix "rabbitmq:management")
DOCKER_IMAGE_METIS=$(add_mirror_prefix "bklite/metis")
DOCKER_IMAGE_VICTORIALOGS=$(add_mirror_prefix "victoriametrics/victoria-logs:v1.25.0")
DOCKER_IMAGE_MLFLOW=$(add_mirror_prefix "bklite/mlflow")
DOCKER_IMAGE_NATS_EXECUTOR=$(add_mirror_prefix "bklite/nats-executor")
DOCKER_IMAGE_FALKORDB=$(add_mirror_prefix "falkordb/falkordb:v4.12.4")
DOCKER_IMAGE_PGVECTOR=$(add_mirror_prefix "pgvector/pgvector:pg15")
DOCKER_IMAGE_TELEGRAF=$(add_mirror_prefix "bklite/telegraf:latest")
DOCKER_IMAGE_VECTOR=$(add_mirror_prefix "timberio/vector:0.48.0-debian")
# 采集器镜像
# TODO: 不同OS/架构支持
export DOCKER_IMAGE_FUSION_COLLECTOR=$(add_mirror_prefix "bklite/fusion-collector:latest")

docker pull $DOCKER_IMAGE_FUSION_COLLECTOR
# 从镜像生成控制器&采集器包
log "INFO" "开始生成控制器和采集器包..."
# 获取当前cpu架构
CPU_ARCH=$(uname -m)
if [[ "$CPU_ARCH" == "x86_64" ]]; then
   [ -d pkgs ] && rm -rvf pkgs
   mkdir -p pkgs/controller
   mkdir -p pkgs/collector
   docker run --rm -v $PWD/pkgs:/pkgs --entrypoint=/bin/bash $DOCKER_IMAGE_FUSION_COLLECTOR -c "cp -av bin/* /pkgs/collector/;cd /opt; cp fusion-collectors/misc/* fusion-collectors/;zip -r /pkgs/controller/fusion-collectors.zip fusion-collectors"
elif [[ "$CPU_ARCH" == "aarch64" ]]; then
   log "WARNING" "当前CPU架构为arm64，暂时无内置采集器"
else
   log "ERROR" "不支持的CPU架构: $CPU_ARCH"
   exit 1
fi

# 检查nats.conf文件是否存在
if [ -f ./conf/nats/nats.conf ]; then
    log "WARNING" "nats.conf文件已存在，文件将被覆盖..."
else
    log "INFO" "创建 nats.conf 文件..."
fi

mkdir -p ./conf/nats
cat > ./conf/nats/nats.conf <<EOF
port: 4222

monitor_port: 8222

trace: true
debug: false
logtime: false

jetstream: enabled
jetstream {
  store_dir=/nats/storage
}

server_name=nats-server
authorization {  
  default_permissions = {
    publish =[]
    subscribe = []
  }
  users = [
    {
      user: "${NATS_ADMIN_USERNAME}"
      password: "${NATS_ADMIN_PASSWORD}"
      permissions: {
        publish = [">"]
        subscribe = [">"]
      }
    },
    {
      user: "${NATS_MONITOR_USERNAME}"
      password: "${NATS_MONITOR_PASSWORD}"
      permissions: {
        publish = ["metrics.>","vector"]
        subscribe = []
      }
    }
  ]
}
EOF

# 生成环境变量文件
log "INFO" "生成 .env 文件..."
cat > .env <<EOF
HOST_IP=${HOST_IP}
TRAEFIK_WEB_PORT=${TRAEFIK_WEB_PORT}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
SECRET_KEY=${SECRET_KEY}
NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
SIDECAR_INIT_TOKEN=${SIDECAR_INIT_TOKEN}
NATS_ADMIN_USERNAME=${NATS_ADMIN_USERNAME}
NATS_ADMIN_PASSWORD=${NATS_ADMIN_PASSWORD}
NATS_MONITOR_USERNAME=${NATS_MONITOR_USERNAME}
NATS_MONITOR_PASSWORD=${NATS_MONITOR_PASSWORD}
MINIO_ROOT_USER=${MINIO_ROOT_USER}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
RABBITMQ_DEFAULT_USER=${RABBITMQ_DEFAULT_USER}
RABBITMQ_DEFAULT_PASSWORD=${RABBITMQ_DEFAULT_PASSWORD}
FALKORDB_PASSWORD=${FALKORDB_PASSWORD}
DOCKER_IMAGE_TRAEFIK=${DOCKER_IMAGE_TRAEFIK}
DOCKER_IMAGE_REDIS=${DOCKER_IMAGE_REDIS}
DOCKER_IMAGE_NATS=${DOCKER_IMAGE_NATS}
DOCKER_IMAGE_NATS_CLI=${DOCKER_IMAGE_NATS_CLI}
DOCKER_IMAGE_VICTORIA_METRICS=${DOCKER_IMAGE_VICTORIA_METRICS}
DOCKER_IMAGE_POSTGRES=${DOCKER_IMAGE_POSTGRES}
DOCKER_IMAGE_SERVER=${DOCKER_IMAGE_SERVER}
DOCKER_IMAGE_WEB=${DOCKER_IMAGE_WEB}
DOCKER_IMAGE_STARGAZER=${DOCKER_IMAGE_STARGAZER}
DOCKER_IMAGE_FUSION_COLLECTOR=${DOCKER_IMAGE_FUSION_COLLECTOR}
DOCKER_IMAGE_MINIO=${DOCKER_IMAGE_MINIO}
DOCKER_IMAGE_RABBITMQ=${DOCKER_IMAGE_RABBITMQ}
DOCKER_IMAGE_METIS=${DOCKER_IMAGE_METIS}
DOCKER_IMAGE_TELEGRAF=${DOCKER_IMAGE_TELEGRAF}
POSTGRES_USERNAME=${POSTGRES_USERNAME}
TRAEFIK_ENABLE_DASHBOARD=${TRAEFIK_ENABLE_DASHBOARD}
DEFAULT_REQUEST_TIMEOUT=${DEFAULT_REQUEST_TIMEOUT}
DIST_ARCH=${DIST_ARCH}
DOCKER_NETWORK=${DOCKER_NETWORK}
DOCKER_IMAGE_VICTORIALOGS=${DOCKER_IMAGE_VICTORIALOGS}
DOCKER_IMAGE_MLFLOW=${DOCKER_IMAGE_MLFLOW}
DOCKER_IMAGE_NATS_EXECUTOR=${DOCKER_IMAGE_NATS_EXECUTOR}
DOCKER_IMAGE_FALKORDB=${DOCKER_IMAGE_FALKORDB}
DOCKER_IMAGE_PGVECTOR=${DOCKER_IMAGE_PGVECTOR}
DOCKER_IMAGE_VECTOR=${DOCKER_IMAGE_VECTOR}

INSTALL_APPS="${INSTALL_APPS}"
EOF

# 生成合成的docker-compose.yaml文件
log "INFO" "生成合成的 docker-compose.yaml 文件..."
$COMPOSE_CMD > docker-compose.yaml

log "INFO" "拉取最新的镜像..."
${DOCKER_COMPOSE_CMD} pull

# 按照特定顺序启动服务
log "INFO" "启动基础服务 (Traefik, Redis, NATS, VictoriaMetrics, FalkorDB, VictoriaLogs, Minio, MLFlow, NATS Executor, Vector)..."
${DOCKER_COMPOSE_CMD} up -d traefik redis nats victoria-metrics falkordb victoria-logs minio mlflow nats-executor vector

# 创建 JetStream - 使用正确的网络名称
log "INFO" "创建JetStream..."
docker run --rm --network=bklite-prod \
    $DOCKER_IMAGE_NATS_CLI -s nats://nats:4222 \
    --user $NATS_ADMIN_USERNAME --password $NATS_ADMIN_PASSWORD \
    stream add metrics --subjects=metrics.* --storage=file \
    --replicas=1 --retention=limits  --discard=old \
    --max-age=20m --max-bytes=104857600 --max-consumers=-1 \
    --max-msg-size=-1 --max-msgs=-1 --max-msgs-per-subject=1000000 \
    --dupe-window=5m --no-allow-rollup --no-deny-delete --no-deny-purge

log "INFO" "启动所有服务"
${DOCKER_COMPOSE_CMD} up -d
sleep 10

log "INFO" "开始初始化内置插件"
$DOCKER_COMPOSE_CMD exec -T server /bin/bash -s <<EOF
uv run manage.py controller_package_init --pk_version latest --file_path /apps/pkgs/controller/fusion-collectors.zip
uv run manage.py collector_package_init --os linux --object Telegraf --pk_version latest --file_path /apps/pkgs/collector/telegraf
uv run manage.py collector_package_init --os linux --object Vector --pk_version latest --file_path /apps/pkgs/collector/vector
uv run manage.py collector_package_init --os linux --object Nats-Executor --pk_version latest --file_path /apps/pkgs/collector/nats-executor
EOF

log "SUCCESS" "部署成功，访问 http://$HOST_IP:$TRAEFIK_WEB_PORT 访问系统"
log "SUCCESS" "初始用户名: admin, 初始密码: password"
log "SUCCESS" "控制器安装信息："
log "SUCCESS" "Token: ${SIDECAR_INIT_TOKEN}"
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

# Function to validate environment variables
validate_env_var() {
    local var_name="$1"
    if [ -z "${!var_name}" ]; then
        log "ERROR" "Environment variable $var_name is not set."
        exit 1
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
    until [ "$(docker-compose ps $container_name --format "{{.Health}}" 2>/dev/null)" == "healthy" ]; do
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
    DEFAULT_IP=$(hostname -I | awk '{print $1}')

    # 从命令行读取HOST_IP环境变量
    read -p "输入对外访问的IP地址，默认为 [$DEFAULT_IP] " HOST_IP
    export HOST_IP=${HOST_IP:-$DEFAULT_IP}

    DEFAULT_TRAEFIK_KEYCLOAK_PORT=20000
    read -p "输入Keycloak端口，默认为 [$DEFAULT_TRAEFIK_KEYCLOAK_PORT] " TRAEFIK_KEYCLOAK_PORT
    export TRAEFIK_KEYCLOAK_PORT=${TRAEFIK_KEYCLOAK_PORT:-$DEFAULT_TRAEFIK_KEYCLOAK_PORT}

    DEFAULT_TRAEFIK_SYSTEM_MANAGER_PORT=20001
    read -p "输入系统管理端口，默认为 [$DEFAULT_TRAEFIK_SYSTEM_MANAGER_PORT] " TRAEFIK_SYSTEM_MANAGER_PORT
    export TRAEFIK_SYSTEM_MANAGER_PORT=${TRAEFIK_SYSTEM_MANAGER_PORT:-$DEFAULT_TRAEFIK_SYSTEM_MANAGER_PORT}

    DEFAULT_TRAEFIK_NODE_MANAGER_PORT=20002
    read -p "输入节点管理端口，默认为 [$DEFAULT_TRAEFIK_NODE_MANAGER_PORT] " TRAEFIK_NODE_MANAGER_PORT
    export TRAEFIK_NODE_MANAGER_PORT=${TRAEFIK_NODE_MANAGER_PORT:-$DEFAULT_TRAEFIK_NODE_MANAGER_PORT}

    DEFAULT_TRAEFIK_MONITOR_PORT=20003
    read -p "输入监控端口，默认为 [$DEFAULT_TRAEFIK_MONITOR_PORT] " TRAEFIK_MONITOR_PORT
    export TRAEFIK_MONITOR_PORT=${TRAEFIK_MONITOR_PORT:-$DEFAULT_TRAEFIK_MONITOR_PORT}

    DEFAULT_TRAEFIK_CONSOLE_PORT=20004
    read -p "输入控制台端口，默认为 [$DEFAULT_TRAEFIK_CONSOLE_PORT] " TRAEFIK_CONSOLE_PORT
    export TRAEFIK_CONSOLE_PORT=${TRAEFIK_CONSOLE_PORT:-$DEFAULT_TRAEFIK_CONSOLE_PORT}

    DEFAULT_NODE_MANAGER_API_PORT=20005
    read -p "输入节点管理API端口，默认为 [$DEFAULT_NODE_MANAGER_API_PORT] " NODE_MANAGER_API_PORT
    export NODE_MANAGER_API_PORT=${NODE_MANAGER_API_PORT:-$DEFAULT_NODE_MANAGER_API_PORT}

    DEFAULT_TRAEFIK_DASHBOARD_PORT=21000
    read -p "输入Traefik Dashboard端口，默认为 [$DEFAULT_TRAEFIK_DASHBOARD_PORT] " TRAEFIK_DASHBOARD_PORT
    export TRAEFIK_DASHBOARD_PORT=${TRAEFIK_DASHBOARD_PORT:-$DEFAULT_TRAEFIK_DASHBOARD_PORT}

    # 将输入的配置写入port.env
    cat > port.env <<EOF
HOST_IP=${HOST_IP}
TRAEFIK_KEYCLOAK_PORT=${TRAEFIK_KEYCLOAK_PORT}
TRAEFIK_SYSTEM_MANAGER_PORT=${TRAEFIK_SYSTEM_MANAGER_PORT}
TRAEFIK_NODE_MANAGER_PORT=${TRAEFIK_NODE_MANAGER_PORT}
TRAEFIK_MONITOR_PORT=${TRAEFIK_MONITOR_PORT}
TRAEFIK_CONSOLE_PORT=${TRAEFIK_CONSOLE_PORT}
NODE_MANAGER_API_PORT=${NODE_MANAGER_API_PORT}
TRAEFIK_DASHBOARD_PORT=${TRAEFIK_DASHBOARD_PORT}
EOF
fi

# 检查common.env文件是否存在，存在则加载，不存在则生成
COMMON_ENV_FILE="common.env"
if [ -f "$COMMON_ENV_FILE" ]; then
    log "SUCCESS" "发现 $COMMON_ENV_FILE 配置文件，加载已保存的环境变量..."
    source $COMMON_ENV_FILE
else
    log "INFO" "未发现 $COMMON_ENV_FILE 配置文件，生成随机环境变量..."
    # 生成随机密码
    export POSTGRES_PASSWORD=$(generate_password 32)
    export REDIS_PASSWORD=$(generate_password 32)
    export KEYCLOAK_PASSWORD=$(generate_password 32)
    export SECRET_KEY=$(generate_password 32)
    export NEXTAUTH_SECRET=$(generate_password 12)
    export SIDECAR_INIT_TOKEN=$(generate_password 64)
    export NATS_USERNAME=admin
    export NATS_PASSWORD=$(generate_password 32)
    export NEO4J_AUTH=neo4j/$(generate_password 32)
    
    # 保存到common.env文件
    cat > $COMMON_ENV_FILE <<EOF
# 自动生成的环境变量配置，用于确保脚本幂等性
# 生成日期: $(date +'%Y-%m-%d %H:%M:%S')
export POSTGRES_PASSWORD=$POSTGRES_PASSWORD
export REDIS_PASSWORD=$REDIS_PASSWORD
export KEYCLOAK_PASSWORD=$KEYCLOAK_PASSWORD
export SECRET_KEY=$SECRET_KEY
export NEXTAUTH_SECRET=$NEXTAUTH_SECRET
export SIDECAR_INIT_TOKEN=$SIDECAR_INIT_TOKEN
export NATS_USERNAME=$NATS_USERNAME
export NATS_PASSWORD=$NATS_PASSWORD
export NEO4J_AUTH=$NEO4J_AUTH
EOF
    log "SUCCESS" "环境变量已生成并保存到 $COMMON_ENV_FILE 文件"
fi

# 固定的环境变量
export DOCKER_IMAGE_TRAEFIK=traefik:3.3.3
export DOCKER_IMAGE_REDIS=redis:5.0.14
export DOCKER_IMAGE_NATS=nats:2.10.25
export DOCKER_IMAGE_NATS_CLI=bitnami/natscli:0.1.6
export DOCKER_IMAGE_VICTORIA_METRICS=victoriametrics/victoria-metrics:v1.106.1
export DOCKER_IMAGE_POSTGRES=postgres:15
export DOCKER_IMAGE_KEYCLOAK=bklite/keycloak
export DOCKER_IMAGE_SYSTEM_MANAGER=bklite/system-manager
export DOCKER_IMAGE_SYSTEM_MANAGER_WEB=bklite/system-manager-web
export DOCKER_IMAGE_NODE_MANAGER=bklite/node-manager
export DOCKER_IMAGE_NODE_MANAGER_WEB=bklite/node-manager-web
export DOCKER_IMAGE_MONITOR=bklite/monitor
export DOCKER_IMAGE_MONITOR_WEB=bklite/monitor-web
export DOCKER_NETWORK=prod
export DIST_ARCH=arm64
export POSTGRES_USERNAME=postgres
export TRAEFIK_ENABLE_DASHBOARD=true
export KEYCLOAK_HOSTNAME=http://${HOST_IP}:${TRAEFIK_KEYCLOAK_PORT}
export KEYCLOAK_USERNAME=admin
export KEYCLOAK_WEB_CLIENT=lite
export DEFAULT_REQUEST_TIMEOUT=10
export DOCKER_IMAGE_OPSCONSOLE=bklite/ops-console
export DOCKER_IMAGE_OPSCONSOLE_WEB=bklite/opsconsole-web
export DOCKER_IMAGE_STARGAZER=bklite/stargazer

# 采集器镜像
# TODO: 不同OS/架构支持
export DOCKER_IMAGE_FUSION_COLLECTOR=bklite/fusion-collector:linux-amd64

# 从镜像生成控制器&采集器包
log "INFO" "开始生成控制器和采集器包..."
[ -d pkgs ] && rm -rvf pkgs
mkdir -p pkgs/controller
mkdir -p pkgs/collector
docker run --rm -v $PWD/pkgs:/pkgs --entrypoint=/bin/bash $DOCKER_IMAGE_FUSION_COLLECTOR -c "tar -czvf /pkgs/controller/lite_controller_linux_amd64.tar.gz . ;cp -av bin/* /pkgs/collector/"

# 检查docker-compose.yml文件是否已存在
if [ -f docker-compose.yml ]; then
    log "INFO" "docker-compose.yml文件已存在，跳过文件生成步骤..."
else
    # 创建 docker-compose.yml 文件
    log "INFO" "创建 docker-compose.yml 文件..."
    cat > docker-compose.yml <<EOF
networks:
  prod:
    driver: bridge

volumes:
  redis:
  nats:
  victoria-metrics:
  postgres:
  neo4j:

services:

  traefik:
    image: ${DOCKER_IMAGE_TRAEFIK}
    restart: always
    ports:
      - "${TRAEFIK_KEYCLOAK_PORT}:${TRAEFIK_KEYCLOAK_PORT}"
      - "${TRAEFIK_SYSTEM_MANAGER_PORT}:${TRAEFIK_SYSTEM_MANAGER_PORT}"
      - "${TRAEFIK_NODE_MANAGER_PORT}:${TRAEFIK_NODE_MANAGER_PORT}"
      - "${TRAEFIK_MONITOR_PORT}:${TRAEFIK_MONITOR_PORT}"
      - "${TRAEFIK_DASHBOARD_PORT}:${TRAEFIK_DASHBOARD_PORT}"
      - "${TRAEFIK_CONSOLE_PORT}:${TRAEFIK_CONSOLE_PORT}"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./conf/traefik/dynamic.yml:/etc/traefik/dynamic.yml
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.traefik-dashboard.rule=Host(\`${HOST_IP}\`)"
      - "traefik.http.routers.traefik-dashboard.entrypoints=traefik-dashboard"
      - "traefik.http.services.traefik-dashboard.loadbalancer.server.port=8080"
    command:
      - "--log.level=INFO"
      - "--api.insecure=true"
      - "--api.dashboard=${TRAEFIK_ENABLE_DASHBOARD}"
      - "--providers.docker.endpoint=unix:///var/run/docker.sock"
      - "--providers.docker.exposedByDefault=false"
      - "--providers.file.filename=/etc/traefik/dynamic.yml"
      - "--providers.file.watch=true"
      - "--accesslog"
      - "--entrypoints.keycloak.address=:${TRAEFIK_KEYCLOAK_PORT}"
      - "--entrypoints.system-manager-web.address=:${TRAEFIK_SYSTEM_MANAGER_PORT}"
      - "--entrypoints.node-manager-web.address=:${TRAEFIK_NODE_MANAGER_PORT}"
      - "--entrypoints.monitor-web.address=:${TRAEFIK_MONITOR_PORT}"
      - "--entrypoints.opsconsole.address=:${TRAEFIK_CONSOLE_PORT}"
      - "--entrypoints.traefik-dashboard.address=:${TRAEFIK_DASHBOARD_PORT}"
    networks:
      - prod

  redis:
    image: ${DOCKER_IMAGE_REDIS}
    restart: always
    volumes:
      - redis:/data
    command:
      - "redis-server"
      - "--requirepass"
      - "${REDIS_PASSWORD}"
    ports:
      - "6379:6379"
    networks:
      - prod

  nats:
    image: ${DOCKER_IMAGE_NATS}
    restart: always
    volumes:
      - ./conf/nats/nats.conf:/etc/nats/nats.conf
      - nats:/nats
    ports:
      - "4222:4222"
    command:
      - "-c"
      - "/etc/nats/nats.conf"
      - "--user"
      - "${NATS_USERNAME}"
      - "--pass"
      - "${NATS_PASSWORD}"
    networks:
      - prod

  victoria-metrics:
    image: ${DOCKER_IMAGE_VICTORIA_METRICS}
    restart: always
    volumes:
      - victoria-metrics:/victoria-metrics-data
    ports:
      - "8428:8428"
    command:
      - "--storageDataPath=/victoria-metrics-data"
      - "--httpListenAddr=0.0.0.0:8428"
      - "--retentionPeriod=168h"
      - "-maxLabelsPerTimeseries=300"
    networks:
      - prod
    depends_on:
      - nats

  neo4j:
    image: neo4j:4.3.3
    container_name: neo4j
    restart: always
    ports:
      - "7474:7474"
      - "7687:7687"
      - "7473:7473"
    networks:
      - prod
    environment:
      - NEO4J_AUTH=${NEO4J_AUTH}
    volumes:
      - neo4j:/data

  postgres:
    container_name: postgres
    image: postgres:15
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGDATA: /data/postgres
    volumes:
       - postgres:/data/postgres
    networks:
      - prod
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USERNAME}"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: always


  keycloak:
    image: ${DOCKER_IMAGE_KEYCLOAK}
    restart: always
    environment:
      KC_DB: postgres
      KC_HOSTNAME: ${KEYCLOAK_HOSTNAME}
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: ${POSTGRES_USERNAME}
      KC_DB_PASSWORD: ${POSTGRES_PASSWORD}
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_USERNAME}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_PASSWORD}
      KC_PROXY_HEADERS: forwarded
      KC_HOSTNAME_STRICT: "false"
      KC_HTTP_ENABLED: "true"
    command: start
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.keycloak.rule=Host(\`${HOST_IP}\`)"
      - "traefik.http.routers.keycloak.entrypoints=keycloak"
      - "traefik.http.services.keycloak.loadbalancer.server.port=8080"
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      postgres:
        condition: service_healthy

  system-manager:
    image: ${DOCKER_IMAGE_SYSTEM_MANAGER}
    restart: always
    environment:
      NATS_SERVERS: nats://${NATS_USERNAME}:${NATS_PASSWORD}@nats:4222
      NATS_NAMESPACE: system_mgmt
      DEFAULT_REQUEST_TIMEOUT: ${DEFAULT_REQUEST_TIMEOUT}
      DB_NAME: system_mgmt
      CLIENT_ID: system-manager
      KEYCLOAK_URL_API: ${KEYCLOAK_HOSTNAME}
      KEYCLOAK_REALM: lite
      KEYCLOAK_CLIENT_ID: lite
      KEYCLOAK_ADMIN_USERNAME: ${KEYCLOAK_USERNAME}
      KEYCLOAK_ADMIN_PASSWORD: ${KEYCLOAK_PASSWORD}
      DEBUG: "0"
      SECRET_KEY: ${SECRET_KEY}
      IS_USE_CELERY: "True"
      DB_USER: ${POSTGRES_USERNAME}
      DB_HOST: postgres
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_PORT: "5432"
      DB_ENGINE: postgresql
    volumes:
      - ./keycloak_web_secret.env:/tmp/keycloak_web_secret.env
    healthcheck:
      test: ["CMD", "curl", "-s", "-o", "/dev/null", "-w", "'%{http_code}'", "http://127.0.0.1:8000/"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      - keycloak

  system-manager-web:
    image: ${DOCKER_IMAGE_SYSTEM_MANAGER_WEB}
    restart: always
    environment:
      KEYCLOAK_CLIENT_ID: lite
      KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_WEB_CLIENT_SECRET:-}
      KEYCLOAK_ISSUER: ${KEYCLOAK_HOSTNAME}/realms/lite
      NEXTAUTH_URL: http://${HOST_IP}:${TRAEFIK_SYSTEM_MANAGER_PORT}
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      NEXTAPI_URL: http://system-manager:8000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.system-manager-web.rule=Host(\`${HOST_IP}\`)"
      - "traefik.http.routers.system-manager-web.entrypoints=system-manager-web"
      - "traefik.http.services.system-manager-web.loadbalancer.server.port=3000"
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      - system-manager

  node-manager:
    image: ${DOCKER_IMAGE_NODE_MANAGER}
    restart: always
    ports:
      - "${NODE_MANAGER_API_PORT}:8000"
    environment:
      NATS_SERVERS: nats://${NATS_USERNAME}:${NATS_PASSWORD}@nats:4222
      NATS_NAMESPACE: node_mgmt
      DB_NAME: node_mgmt
      CLIENT_ID: node_mgmt
      SIDECAR_INIT_TOKEN: ${SIDECAR_INIT_TOKEN}
      DEFAULT_ZONE_VAR_NATS_SERVERS: nats://${HOST_IP}:4222
      DEFAULT_ZONE_VAR_NATS_USERNAME: ${NATS_USERNAME}
      DEFAULT_ZONE_VAR_NATS_PASSWORD: ${NATS_PASSWORD}
      DEFAULT_ZONE_VAR_NODE_SERVER_URL: http://${HOST_IP}:${NODE_MANAGER_API_PORT}
      DEFAULT_ZONE_VAR_STARGAZER_URL: http://stargazer:8083
      SIDECAR_INPUT_MODE: nats
      DEBUG: "0"
      SECRET_KEY: ${SECRET_KEY}
      IS_USE_CELERY: "False"
      DB_USER: ${POSTGRES_USERNAME}
      DB_HOST: postgres
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_PORT: "5432"
      DB_ENGINE: postgresql
    volumes:
      - ./pkgs:/pkgs
    healthcheck:
      test: ["CMD", "curl", "-s", "-o", "/dev/null", "-w", "'%{http_code}'", "http://127.0.0.1:8000/"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      - system-manager

  node-manager-web:
    image: ${DOCKER_IMAGE_NODE_MANAGER_WEB}
    restart: always
    environment:
      KEYCLOAK_CLIENT_ID: lite
      KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_WEB_CLIENT_SECRET:-}
      KEYCLOAK_ISSUER: ${KEYCLOAK_HOSTNAME}/realms/lite
      NEXTAUTH_URL: http://${HOST_IP}:${TRAEFIK_NODE_MANAGER_PORT}
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      NEXTAPI_URL: http://node-manager:8000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.node-manager-web.rule=Host(\`${HOST_IP}\`)"
      - "traefik.http.routers.node-manager-web.entrypoints=node-manager-web"
      - "traefik.http.services.node-manager-web.loadbalancer.server.port=3000"
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      - node-manager

  monitor:
    image: ${DOCKER_IMAGE_MONITOR}
    restart: always
    environment:
      NATS_SERVERS: nats://${NATS_USERNAME}:${NATS_PASSWORD}@nats:4222
      NATS_NAMESPACE: monitor
      CLIENT_ID: monitor
      DB_NAME: monitor
      VICTORIAMETRICS_HOST: http://victoria-metrics:8428
      IS_USE_CELERY: "True"
      BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/10
      CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@redis:6379/10
      CELERY_RESULT_BACKEND: redis://:${REDIS_PASSWORD}@redis:6379/10
      DEBUG: "0"
      SECRET_KEY: ${SECRET_KEY}
      DB_ENGINE: postgresql
      DB_USER: ${POSTGRES_USERNAME}
      DB_HOST: postgres
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_PORT: "5432"
    healthcheck:
      test: ["CMD", "curl", "-s", "-o", "/dev/null", "-w", "'%{http_code}'", "http://127.0.0.1:8000/"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    networks:
      - prod
    profiles:
      - lite

  monitor-web:
    image: ${DOCKER_IMAGE_MONITOR_WEB}
    restart: always
    environment:
      KEYCLOAK_CLIENT_ID: ${KEYCLOAK_WEB_CLIENT}
      KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_WEB_CLIENT_SECRET:-}
      KEYCLOAK_ISSUER: ${KEYCLOAK_HOSTNAME}/realms/lite
      NEXTAUTH_URL: http://${HOST_IP}:${TRAEFIK_MONITOR_PORT}
      NEXTAUTH_SECRET: ${NEXTAUTH_SECRET}
      NEXTAPI_URL: http://monitor:8000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.monitor-web.rule=Host(\`${HOST_IP}\`)"
      - "traefik.http.routers.monitor-web.entrypoints=monitor-web"
      - "traefik.http.services.monitor-web.loadbalancer.server.port=3000"
    networks:
      - prod
    profiles:
      - lite
    depends_on:
      - monitor

  telegraf:
    image: bklite/telegraf
    container_name: telegraf
    environment:
      - METRIC_NATS_USERNAME=admin
      - METRIC_NATS_PASSWORD=${NATS_PASSWORD}
      - METRIC_OUTPUT_URL=http://victoria-metrics:8428
      - METRIC_NATS_SERVERS=nats://nats:4222
    volumes:
      - ./conf/telegraf/telegraf.conf:/etc/telegraf/telegraf.conf
    networks:
      - prod
    profiles:
      - lite
    restart: always

  ops-console:
    image: ${DOCKER_IMAGE_OPSCONSOLE}
    restart: always
    environment:
      NATS_SERVERS: nats://${NATS_USERNAME}:${NATS_PASSWORD}@nats:4222
      NATS_NAMESPACE: ops-console
      CLIENT_ID: ops-console
      DB_NAME: ops-console
      DB_USER: ${POSTGRES_USERNAME}
      DB_HOST: postgres
      DB_PASSWORD: ${POSTGRES_PASSWORD}
      DB_ENGINE: postgresql
      DB_PORT: "5432"
      DEBUG: "0"
      SECRET_KEY: ${SECRET_KEY}
    networks:
      - prod
    healthcheck:
      test: ["CMD", "curl", "-s", "-o", "/dev/null", "-w", "'%{http_code}'", "http://127.0.0.1:8000/"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    profiles:
      - lite
    
  ops-console-web:
    image: bklite/ops-console-web
    container_name: ops-console-web
    environment:
      - NEXTAPI_URL=http://ops-console:8000
      - KEYCLOAK_CLIENT_ID=${KEYCLOAK_WEB_CLIENT}
      - KEYCLOAK_CLIENT_SECRET=${KEYCLOAK_WEB_CLIENT_SECRET:-}
      - KEYCLOAK_ISSUER=http://${KEYCLOAK_HOSTNAME}/realms/lite
      - NEXTAUTH_URL=https://${HOST_IP}:${TRAEFIK_CONSOLE_PORT}
      - NEXTAUTH_SECRET=${NEXTAUTH_SECRET}
      - NEXTAPI_URL=http://ops-console:8000
    restart: always
    networks:
      - prod
    labels:
      - traefik.enable=true
      - traefik.http.routers.ops-console-web.rule=Host(\`${HOST_IP}\`)
      - traefik.http.routers.ops-console-web.entrypoints=ops-console-web
      - traefik.http.services.ops-console-web.loadbalancer.server.port=3000

  stargazer:
    image: ${DOCKER_IMAGE_STARGAZER}
    container_name: stargazer
    networks:
      - prod

EOF
fi

# 按照特定顺序启动服务
log "INFO" "启动基础服务 (Traefik, Redis, NATS, VictoriaMetrics)..."
docker-compose up -d traefik redis nats victoria-metrics

# 获取 Docker Compose 创建的网络名称
PROJECT_NAME=$(basename $(pwd))
COMPOSE_NETWORK=${PROJECT_NAME}_prod

# 创建 JetStream - 使用正确的网络名称
log "INFO" "创建JetStream..."
docker run --rm --network=${COMPOSE_NETWORK} \
    $DOCKER_IMAGE_NATS_CLI -s nats://nats:4222 \
    --user $NATS_USERNAME --password $NATS_PASSWORD \
    stream add metrics --subjects=metrics.* --storage=file \
    --replicas=1 --retention=limits  --discard=old \
    --max-age=20m --max-bytes=104857600 --max-consumers=-1 \
    --max-msg-size=-1 --max-msgs=-1 --max-msgs-per-subject=1000000 \
    --dupe-window=5m --no-allow-rollup --no-deny-delete --no-deny-purge

# 启动 Postgres 并等待服务就绪
log "INFO" "启动 Postgres..."
docker-compose up -d postgres
wait_container_health postgres "Postgres"

# 创建所有必要的数据库 - 使用一条命令创建多个数据库
log "INFO" "创建必要的数据库..."
docker-compose exec -T postgres psql -U "$POSTGRES_USERNAME" -d postgres <<-'EOSQL'
CREATE DATABASE system_mgmt;
CREATE DATABASE node_mgmt;
CREATE DATABASE monitor;
CREATE DATABASE "ops-console";
CREATE DATABASE keycloak;
EOSQL

# 启动 Keycloak 并等待其响应
log "INFO" "启动 KeyCloak..."
docker-compose up -d keycloak
# 等待 Keycloak 启动
check_http_response $KEYCLOAK_HOSTNAME 302 "KeyCloak" 120

# 先导出环境变量，避免docker-compose警告
# 在执行system-manager-init之前，创建一个临时的空文件，如果文件不存在的话
if [ ! -f keycloak_web_secret.env ]; then
    log "INFO" "创建临时的keycloak_web_secret.env文件..."
    touch keycloak_web_secret.env
    echo "KEYCLOAK_WEB_CLIENT_SECRET=" > keycloak_web_secret.env
fi

# 启动系统管理服务初始化
log "INFO" "执行系统管理服务初始化..."
docker run --rm \
    --network=${COMPOSE_NETWORK} \
    -v $(pwd)/keycloak_web_secret.env:/tmp/keycloak_web_secret.env \
    -e NATS_SERVERS="nats://${NATS_USERNAME}:${NATS_PASSWORD}@nats:4222" \
    -e NATS_NAMESPACE="system_mgmt" \
    -e DEFAULT_REQUEST_TIMEOUT="${DEFAULT_REQUEST_TIMEOUT}" \
    -e DB_NAME="system_mgmt" \
    -e CLIENT_ID="system-manager" \
    -e KEYCLOAK_URL_API="${KEYCLOAK_HOSTNAME}" \
    -e KEYCLOAK_REALM="lite" \
    -e KEYCLOAK_CLIENT_ID="lite" \
    -e KEYCLOAK_ADMIN_USERNAME="${KEYCLOAK_USERNAME}" \
    -e KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_PASSWORD}" \
    -e DEBUG="0" \
    -e SECRET_KEY="${SECRET_KEY}" \
    -e IS_USE_CELERY="True" \
    -e DB_USER="${POSTGRES_USERNAME}" \
    -e DB_HOST="postgres" \
    -e DB_PASSWORD="${POSTGRES_PASSWORD}" \
    -e DB_PORT="5432" \
    -e DB_ENGINE="postgresql" \
    --entrypoint="/bin/bash" \
    ${DOCKER_IMAGE_SYSTEM_MANAGER} -c "python manage.py init_realm && python manage.py init_realm_resource"

# 获取 Keycloak Web Client Secret 并设置
export KEYCLOAK_WEB_CLIENT_SECRET=$(cat keycloak_web_secret.env | grep KEYCLOAK_WEB_CLIENT_SECRET | cut -d '=' -f 2)
log "INFO" "Keycloak Web Client Secret: $KEYCLOAK_WEB_CLIENT_SECRET"

# 重新渲染compose文件里的KEYCLOAK_WEB_CLIENT_SECRET
sed -i "s|KEYCLOAK_CLIENT_SECRET: .*|KEYCLOAK_CLIENT_SECRET: ${KEYCLOAK_WEB_CLIENT_SECRET}|" docker-compose.yml
log "INFO" "KEYCLOAK_WEB_CLIENT_SECRET已更新"

# 继续启动其他服务
log "INFO" "启动系统管理服务..."
docker-compose up -d system-manager
wait_container_health system-manager "系统管理服务"

log "INFO" "启动系统管理Web..."
docker-compose up -d system-manager-web

log "INFO" "启动节点管理..."
docker-compose up -d node-manager
wait_container_health node-manager "节点管理"

log "INFO" "启动节点管理Web..."
docker-compose up -d node-manager-web

# TODO: 兼容多架构,windows
# log "INFO" "初始化节点管理插件包..."
# docker-compose exec node-manager bash -c 'python manage.py controller_package_init --os "linux" --pk_version "0.0.1" --file_path "/pkgs/controller/lite_controller_linux_amd64.tar.gz"'
# docker-compose exec node-manager bash -c 'python manage.py collector_package_init --os "linux"  --object "Telegraf" --pk_version "0.0.1" --file_path "/pkgs/collector/telegraf"'

log "INFO" "启动监控系统..."
docker-compose up -d monitor
wait_container_health monitor "监控系统"

log "INFO" "启动监控系统Web..."
docker-compose up -d monitor-web

log "INFO" "启动控制台..."
docker-compose up -d ops-console
wait_container_health ops-console "OpsConsole"

log "INFO" "启动控制台Web..."
docker-compose up -d ops-console-web

log "INFO" "启动telegraf..."
docker-compose up -d telegraf

log "INFO" "启动stargazer..."
docker-compose up -d stargazer

log "SUCCESS" "部署成功，访问 http://$HOST_IP:$TRAEFIK_MONITOR_PORT 访问系统"
log "INFO" "初始用户名: admin, 初始密码: password"
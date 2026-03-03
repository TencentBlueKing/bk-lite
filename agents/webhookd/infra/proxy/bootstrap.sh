#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

MAX_WAIT=60
MAX_SYNC_WAIT=300
RETRY_INTERVAL=2

R='\033[0;31m' G='\033[0;32m' B='\033[0;34m' N='\033[0m'
log() { echo -e "${2}[$(date +%H:%M:%S)] $1${N}"; }
info() { log "$1" "$B"; }
ok()   { log "$1" "$G"; }
err()  { log "$1" "$R"; exit 1; }

retry() {
    local max=$1 interval=$2 desc=$3; shift 3
    local elapsed=0
    while ! "$@" 2>/dev/null; do
        elapsed=$((elapsed + interval))
        [ $elapsed -ge $max ] && return 1
        info "$desc... (${elapsed}s/${max}s)"
        sleep $interval
    done
    return 0
}

nats_cmd() {
    docker run --rm --network=bklite-proxy \
        -v "$PWD/conf/certs/ca.crt:/tmp/nats/ca.crt" \
        bk-lite.tencentcloudcr.com/bklite/natsio/nats-box \
        nats -s tls://nats:4222 \
        --user admin --password "${NATS_ADMIN_PASSWORD}" \
        --tlsca /tmp/nats/ca.crt "$@"
}

check_services() {
    local failed=0
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local name state
        name=$(echo "$line" | awk '{print $1}')
        state=$(echo "$line" | awk '{print $NF}')
        if [[ "$state" =~ ^(running|Up)$ ]]; then
            ok "$name: $state"
        else
            log "$name: $state" "$R"
            failed=1
        fi
    done < <($DC ps --format "table {{.Name}}\t{{.State}}" 2>/dev/null | tail -n +2)
    return $failed
}

get_lag() {
    nats_cmd stream state OBJ_bklite 2>/dev/null | grep Lag | awk '{print $2}'
}

[ -f .env ] || err ".env not found"
set -a; source .env; set +a

if command -v docker-compose &>/dev/null; then
    DC="docker-compose"
elif docker compose version &>/dev/null; then
    DC="docker compose"
else
    err "docker compose not found"
fi

info "Starting services..."
$DC up -d || err "Failed to start"

info "Waiting for services to be ready..."
retry $MAX_WAIT $RETRY_INTERVAL "Waiting for containers" check_services \
    || err "Services failed to start within ${MAX_WAIT}s"
ok "All services running"

info "Initializing JetStream Object Storage..."
retry 30 $RETRY_INTERVAL "Connecting to NATS" \
    nats_cmd stream ls || err "Cannot connect to NATS"

if ! nats_cmd stream info OBJ_bklite &>/dev/null; then
    docker run --rm --network=bklite-proxy \
        -v "$PWD/conf/certs/ca.crt:/tmp/nats/ca.crt" \
        -v "$PWD/conf/nats/jetstream.json:/tmp/nats/jetstream.json" \
        bk-lite.tencentcloudcr.com/bklite/natsio/nats-box \
        nats -s tls://nats:4222 \
        --user admin --password "${NATS_ADMIN_PASSWORD}" \
        --tlsca /tmp/nats/ca.crt \
        stream add --config /tmp/nats/jetstream.json \
    || err "Failed to create JetStream stream"
    ok "JetStream stream created"
else
    ok "JetStream stream already exists"
fi

info "Waiting for JetStream sync..."
elapsed=0
while true; do
    lag=$(get_lag)
    [ "$lag" = "0" ] && break
    
    elapsed=$((elapsed + RETRY_INTERVAL))
    [ $elapsed -ge $MAX_SYNC_WAIT ] && err "JetStream sync timeout (${MAX_SYNC_WAIT}s)"
    
    info "Syncing... LAG: ${lag:-unknown} (${elapsed}s/${MAX_SYNC_WAIT}s)"
    sleep $RETRY_INTERVAL
done
ok "JetStream sync complete"

info "Copying binaries to host..."
docker run --rm --network=bklite-proxy \
    -v "$PWD/bin:/tmp/bin" \
    --entrypoint=/bin/bash \
    "$DOCKER_IMAGE_FUSION_COLLECTOR" \
    -c "cp -ar bin/* /tmp/bin/" \
|| err "Failed to copy binaries"

ok "Done"

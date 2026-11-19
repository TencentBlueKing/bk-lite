#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

err() { printf 'Proxy: %s\n' "$1" >&2; exit 1; }

[ -r .env ] || err ".env not found"
command -v jq >/dev/null || err "jq is required"
docker compose version >/dev/null || err "Docker Compose is required"

# Read resolved values without executing a dotenv file as a shell program.
load_compose_env() {
    local config
    config=$(docker compose --project-directory "$1" config --format json 2>/dev/null) ||
        err "Compose configuration is invalid"
    NATS_ADMIN_USERNAME=$(jq -er '.services["nats-executor"].environment.NATS_URLS | capture("://(?<user>[^:]+):").user' <<< "$config")
    NATS_ADMIN_PASSWORD=$(jq -er '.services["nats-executor"].environment.NATS_URLS | capture("://[^:]+:(?<password>.*)@nats:4222$").password' <<< "$config")
    NATS_IMAGE=$(jq -er '.services.nats.image' <<< "$config")
    COLLECTOR_IMAGE=$(jq -er '.services["fusion-collector"].image' <<< "$config")
    HTTPS_PORT=$(jq -er '
        [.services.traefik.command[] | capture("^--entrypoints[.]websecure[.]address=:(?<port>[0-9]+)$").port]
        | if length == 1 then .[0] else error("missing HTTPS entry point") end
    ' <<< "$config") || err "Cannot determine the Proxy HTTPS entry point"
}

NATS_BOX=bk-lite.tencentcloudcr.com/bklite/natsio/nats-box:latest
load_compose_env "$PWD"
MIRROR=conf/nats/jetstream.json
STREAM=$(jq -er '.name' "$MIRROR")
SOURCE_API=$(jq -er '.mirror.external.api' "$MIRROR")
api() {
    local payload='{}'
    [ "$#" -lt 5 ] || payload=$5
    NATS_USER="$NATS_ADMIN_USERNAME" NATS_PASSWORD="$NATS_ADMIN_PASSWORD" \
        docker run --rm --network "$1" -e NATS_USER -e NATS_PASSWORD \
        -v "$2/conf/certs/ca.crt:/tmp/nats/ca.crt:ro" "$NATS_BOX" \
        nats --no-context --server "tls://$3:4222" --tlsca /tmp/nats/ca.crt --timeout 3s \
        request --raw "$4" "$payload" 2>/dev/null
}

stream_missing() { jq -e '.error.err_code == 10059' >/dev/null <<< "$1"; }

check_mirror() {
    jq -e --arg api "$SOURCE_API" --arg stream "$STREAM" '
        .config.mirror.name == $stream and .config.mirror.external.api == $api
    ' >/dev/null <<< "$1" || err "Existing $STREAM has a different mirror source (messages: $(jq -r '.state.messages // "unknown"' <<< "$1")). Review migration before upgrading."
}

probe_source() (
    local candidate source attempt probe_config
    probe_config=$(mktemp "$PWD/conf/nats/.probe.XXXXXX")
    trap 'if [ -n "${candidate:-}" ]; then docker rm -f "$candidate" >/dev/null 2>&1 || true; fi; rm -f -- "$probe_config"' EXIT
    sed "s/^[[:space:]]*domain: leaf-.*/    domain: proxy-preflight-$BASHPID/" conf/nats/nats.conf > "$probe_config"
    docker run --rm --network none \
        -v "$PWD/conf/nats/nats.conf:/etc/nats/nats.conf:ro" \
        -v "$PWD/conf/certs:/etc/nats/certs:ro" \
        "$NATS_IMAGE" -t -c /etc/nats/nats.conf >/dev/null 2>&1 || err "Candidate NATS configuration failed validation"
    candidate=$(docker run -d --tmpfs /nats \
        -v "$probe_config:/etc/nats/nats.conf:ro" \
        -v "$PWD/conf/certs:/etc/nats/certs:ro" \
        "$NATS_IMAGE" -c /etc/nats/nats.conf 2>/dev/null) || err "Cannot start the temporary NATS check"
    for attempt in {1..8}; do
        if source=$(api "container:$candidate" "$PWD" 127.0.0.1 "$SOURCE_API.STREAM.INFO.$STREAM") &&
            jq -e '(.config.name != null) or (.error.err_code == 10059)' >/dev/null <<< "$source"; then
            break
        fi
        source=
    done
    [ -n "$source" ] || err "Cannot reach the source JetStream domain. Check the Leafnode endpoint, TLS, credentials and domain."
    printf '%s\n' "$source"
)

compose_template_supported() {
    local installed_compose=$1
    cmp -s "$installed_compose" docker-compose.yaml && return 0
    # Normalize only the two known differences in shipped templates.
    sed -e '/^      - "--providers.file.templating=true"$/d' \
        -e 's/^      - "4223:4222"$/      - "4222:4222"/' "$installed_compose" |
        cmp -s - docker-compose.yaml
}

preflight() {
    local installed=$1 source existing
    if [ -f "$installed/docker-compose.yaml" ]; then
        compose_template_supported "$installed/docker-compose.yaml" ||
            err "Installed Compose file differs from the packaged template. Review local overrides before upgrading."
        if grep -Fxq '      - "4223:4222"' "$installed/docker-compose.yaml"; then
            local compose_file
            compose_file=$(mktemp "$PWD/.compose.XXXXXX")
            sed 's/^      - "4222:4222"$/      - "4223:4222"/' docker-compose.yaml > "$compose_file"
            mv -- "$compose_file" docker-compose.yaml
        fi
    fi
    source=$(probe_source) || exit 1
    if [ ! -f "$installed/docker-compose.yaml" ]; then
        [ ! -e "$installed/.env" ] || err "Existing Proxy layout is incomplete"
        return
    fi
    stream_missing "$source" && err "The source stream $STREAM is missing. Restore it before upgrading."
    local installed_stream=$STREAM
    if [ -r "$installed/conf/nats/jetstream.json" ]; then
        installed_stream=$(jq -er '.name' "$installed/conf/nats/jetstream.json")
    fi
    load_compose_env "$installed"
    existing=$(api bklite-proxy "$installed" nats "\$JS.API.STREAM.INFO.$installed_stream") ||
        err "Cannot inspect the installed Proxy mirror. Check the running Proxy before upgrading."
    if ! stream_missing "$existing"; then
        jq -e '.config.name != null' >/dev/null <<< "$existing" || err "Existing stream lookup returned an error"
        check_mirror "$existing"
    fi
}

if [ "${1:-}" = preflight ]; then
    preflight "$2"
    exit
fi

docker compose up -d --force-recreate || err "Services failed to start"
source=
for attempt in {1..8}; do
    if source=$(api bklite-proxy "$PWD" nats "$SOURCE_API.STREAM.INFO.$STREAM") &&
        jq -e '(.config.name != null) or (.error.err_code == 10059)' >/dev/null <<< "$source"; then
        break
    fi
    source=
done
[ -n "$source" ] || err "Source JetStream domain is unreachable"

if stream_missing "$source"; then
    printf 'Proxy started. Source stream %s is pending. Upload the first package and rerun the installer.\n' "$STREAM"
else
    existing=$(api bklite-proxy "$PWD" nats "\$JS.API.STREAM.INFO.$STREAM") || err "Cannot inspect the local mirror"
    if stream_missing "$existing"; then
        created=$(api bklite-proxy "$PWD" nats "\$JS.API.STREAM.CREATE.$STREAM" "$(cat "$MIRROR")") ||
            err "Cannot create the local mirror"
        jq -e '.config.name != null' >/dev/null <<< "$created" || err "JetStream rejected mirror creation"
    else
        check_mirror "$existing"
    fi

    synced=false
    for attempt in {1..60}; do
        if state=$(api bklite-proxy "$PWD" nats "\$JS.API.STREAM.INFO.$STREAM") &&
            jq -e '.mirror.lag == 0 and .mirror.error == null and (.mirror.active // 0) > 0 and .mirror.active < 30000000000' \
                >/dev/null <<< "$state"; then
            synced=true
            break
        fi
        sleep 2
    done
    $synced || err "$STREAM mirror did not synchronize"
    if [ "$(jq -r '.state.messages // 0' <<< "$source")" = 0 ]; then
        printf 'Mirror connected. Upload the first package to verify downloads.\n'
    else
        printf '%s mirror synchronized. Verify an installer download through the Proxy.\n' "$STREAM"
    fi
fi

# Probe the same HTTPS route regional services use, without following redirects
# to a different endpoint or bypassing verification of the Proxy certificate.
proxy_https_ready() {
    local status
    status=$(docker run --rm --network bklite-proxy --entrypoint curl \
        -v "$PWD/conf/certs/ca.crt:/tmp/nats/ca.crt:ro" "$NATS_BOX" \
        --noproxy '*' --silent --connect-timeout 2 --max-time 3 \
        --cacert /tmp/nats/ca.crt --output /dev/null --write-out '%{http_code}' \
        "https://traefik:$HTTPS_PORT/" 2>/dev/null) || return 1
    [[ "$status" =~ ^[23][0-9][0-9]$ ]]
}

# Check the actual project, including exited/restarting containers. The queue
# initializer is one-shot and must exit successfully, not remain running.
wait_for_services() {
    local attempt states consecutive=0 last_failure
    for attempt in {1..31}; do
        if states=$(docker compose ps --all --format json 2>/dev/null) &&
            jq -es '
                [ .[] | if type == "array" then .[] else . end ] as $statuses |
                (["nats","nats-executor","fusion-collector","apm-regional-collector","traefik","stargazer","redis"] |
                    all(. as $service | any($statuses[];
                        .Service == $service and .State == "running" and
                        (if $service == "redis" then .Health == "healthy"
                         else (.Health // "") == "" or .Health == "healthy" end)))) and
                any($statuses[]; .Service == "apm-regional-queue-init" and .State == "exited" and .ExitCode == 0)
            ' >/dev/null <<< "$states"; then
            if proxy_https_ready; then
                consecutive=$((consecutive + 1))
                [ "$consecutive" -lt 2 ] || return 0
                last_failure="Proxy HTTPS route did not stay ready"
            else
                consecutive=0
                last_failure="Proxy HTTPS route is not ready; check the TLS certificate and upstream"
            fi
        else
            consecutive=0
            last_failure="Proxy services are not ready; check docker compose ps --all"
        fi
        [ "$attempt" -eq 31 ] || sleep 2
    done
    err "$last_failure"
}

# Preserve the existing agent binary installation step.
docker run --rm --network=bklite-proxy \
    -v "$PWD/bin:/tmp/bin" --entrypoint=/bin/bash "$COLLECTOR_IMAGE" \
    -c "cp -ar bin/* /tmp/bin/" || err "Failed to copy binaries"

wait_for_services

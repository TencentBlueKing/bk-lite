#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_DIR="${PROXY_TEMPLATE_DIR:-${SCRIPT_DIR}/proxy}"
CA_KEY="${PROXY_CA_KEY_PATH:-/etc/certs/ca.key}"
CA_CRT="${PROXY_CA_CERT_PATH:-/etc/certs/ca.crt}"

die() { echo "{\"status\":\"error\",\"message\":\"$1\"}" >&2; exit 1; }

for cmd in jq openssl tar base64 envsubst; do
    command -v $cmd &>/dev/null || die "$cmd not found"
done

[ -f "$CA_KEY" ] && [ -f "$CA_CRT" ] || die "CA certs not found at /etc/certs/"
[ -d "$PROXY_DIR" ] || die "proxy dir not found"

JSON="${1:-$(cat)}"
[ -n "$JSON" ] || die "no input"
echo "$JSON" | jq empty 2>/dev/null || die "invalid json"

get() { echo "$JSON" | jq -r ".$1 // empty"; }

NODE_ID=$(get node_id)
ZONE_ID=$(get zone_id)
ZONE_NAME=$(get zone_name)
SERVER_URL=$(get server_url)
NATS_URL=$(get nats_url)
NATS_USER=$(get nats_username)
NATS_PASS=$(get nats_password)
API_TOKEN=$(get api_token)
REDIS_PASS=$(get redis_password)
INSTALL_PATH=$(get install_path)
INSTALL_PATH="${INSTALL_PATH:-/opt/bk-lite/proxy}"
PROXY_IP=$(get proxy_ip)
MONITOR_USER=$(get nats_monitor_username)
MONITOR_PASS=$(get nats_monitor_password)
APM_NATS_USER=$(get apm_nats_username)
APM_NATS_PASS=$(get apm_nats_password)
TRAEFIK_WEB_PORT=$(get traefik_web_port)

for p in node_id zone_id zone_name server_url nats_url nats_username nats_password api_token redis_password proxy_ip nats_monitor_username nats_monitor_password apm_nats_username apm_nats_password traefik_web_port; do
    [ -n "$(get $p)" ] || die "missing $p"
done

PROXY_SAN_VALUE="${PROXY_IP#[}"
PROXY_SAN_VALUE="${PROXY_SAN_VALUE%]}"
if [[ "$PROXY_SAN_VALUE" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ || "$PROXY_SAN_VALUE" == *:* ]]; then
    PROXY_SAN="IP:${PROXY_SAN_VALUE}"
else
    PROXY_SAN="DNS:${PROXY_SAN_VALUE}"
fi

NATS_ENDPOINT="${NATS_URL#*://}"
if [[ "$NATS_ENDPOINT" == \[* ]]; then
    NATS_HOST="${NATS_ENDPOINT%%]*}]"
    NATS_REMAINDER="${NATS_ENDPOINT#*]}"
    NATS_PORT="${NATS_REMAINDER#:}"
else
    NATS_HOST="${NATS_ENDPOINT%%:*}"
    NATS_PORT="${NATS_ENDPOINT#*:}"
    [ "$NATS_PORT" = "$NATS_ENDPOINT" ] && NATS_PORT=""
fi
NATS_PORT="${NATS_PORT:-4222}"

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

cp -r "$PROXY_DIR"/* "$WORK/"

openssl genrsa -out "$WORK/conf/certs/proxy.key" 2048 2>/dev/null

cat > "$WORK/proxy.cnf" << EOF
[req]
default_bits=2048
prompt=no
default_md=sha256
distinguished_name=dn
req_extensions=ext
[dn]
CN=${NODE_ID}
[ext]
subjectAltName=DNS:${NODE_ID},DNS:localhost,DNS:nats,DNS:traefik,IP:127.0.0.1,${PROXY_SAN}
EOF

openssl req -new -key "$WORK/conf/certs/proxy.key" -out "$WORK/proxy.csr" -config "$WORK/proxy.cnf" 2>/dev/null
openssl x509 -req -in "$WORK/proxy.csr" -CA "$CA_CRT" -CAkey "$CA_KEY" -CAserial "$WORK/ca.srl" -CAcreateserial \
    -out "$WORK/conf/certs/proxy.crt" -days 365 -extensions ext -extfile "$WORK/proxy.cnf" 2>/dev/null
cp "$CA_CRT" "$WORK/conf/certs/ca.crt"

cp "$WORK/conf/certs/ca.crt" "$WORK/conf/traefik/certs/"
cp "$WORK/conf/certs/proxy.crt" "$WORK/conf/traefik/certs/"
cp "$WORK/conf/certs/proxy.key" "$WORK/conf/traefik/certs/"

# 设置环境变量供 envsubst 使用
export ZONE_ID ZONE_NAME SERVER_URL
export SIDECAR_NODE_ID="${NODE_ID}"
export SIDECAR_NODE_NAME="${NODE_ID}"
export SIDECAR_INIT_TOKEN="${API_TOKEN}"
export NATS_ADMIN_USERNAME="${NATS_USER}"
export NATS_ADMIN_PASSWORD="${NATS_PASS}"
export APM_NATS_USERNAME="${APM_NATS_USER}"
export APM_NATS_PASSWORD="${APM_NATS_PASS}"
export REDIS_PASSWORD="${REDIS_PASS}"
export TRAEFIK_WEB_PORT

envsubst < "$WORK/env.template" > "$WORK/.env"

export REMOTE_HOST="${NATS_HOST}"
export REMOTE_NATS_PORT="${NATS_PORT}"
export NATS_MONITOR_USERNAME="${MONITOR_USER}"
export NATS_MONITOR_PASSWORD="${MONITOR_PASS}"
export APM_NATS_USERNAME APM_NATS_PASSWORD

envsubst < "$WORK/conf/nats/nats.conf.template" > "$WORK/conf/nats/nats.conf"

rm -f "$WORK/proxy.cnf" "$WORK/proxy.csr" "$WORK/env.template" "$WORK/conf/nats/nats.conf.template"

ARCHIVE=$(tar -czf - -C "$WORK" . | base64 | tr -d '\n')

INSTALL_SCRIPT=$(cat << 'SCRIPT'
#!/bin/bash
set -euo pipefail
INSTALL_PATH="__INSTALL_PATH__"
ARCHIVE="__ARCHIVE__"
mkdir -p "$INSTALL_PATH"
echo "$ARCHIVE" | base64 -d | tar -xzf - -C "$INSTALL_PATH"
chmod 600 "$INSTALL_PATH/.env" "$INSTALL_PATH/conf/certs/proxy.key" "$INSTALL_PATH/conf/traefik/certs/proxy.key"
cd "$INSTALL_PATH" && ./bootstrap.sh
SCRIPT
)

INSTALL_SCRIPT="${INSTALL_SCRIPT/__INSTALL_PATH__/$INSTALL_PATH}"
INSTALL_SCRIPT="${INSTALL_SCRIPT/__ARCHIVE__/$ARCHIVE}"

jq -n --arg id "$NODE_ID" --arg script "$INSTALL_SCRIPT" \
    '{status:"success",id:$id,message:"ok",install_script:$script}'

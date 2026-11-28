#!/bin/bash
set -euo pipefail
umask 077

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

get() { printf '%s\n' "$JSON" | jq -r ".$1 // empty"; }
PACKAGE_VERSION=$(jq -er '
    if type != "object" then error("invalid payload")
    elif has("proxy_package_version") then
        if .proxy_package_version == 2 then 2 else error("unsupported version") end
    else 1 end
' <<< "$JSON" 2>/dev/null) || die "unsupported proxy_package_version"

NODE_ID=$(get node_id)
ZONE_ID=$(get zone_id)
ZONE_NAME=$(get zone_name)
SERVER_URL=$(get server_url)
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

for p in node_id zone_id zone_name server_url nats_username nats_password api_token redis_password proxy_ip nats_monitor_username nats_monitor_password apm_nats_username apm_nats_password traefik_web_port; do
    [ -n "$(get $p)" ] || die "missing $p"
done

PROXY_SAN_VALUE="${PROXY_IP#[}"
PROXY_SAN_VALUE="${PROXY_SAN_VALUE%]}"
if [[ "$PROXY_SAN_VALUE" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ || "$PROXY_SAN_VALUE" == *:* ]]; then
    PROXY_SAN="IP:${PROXY_SAN_VALUE}"
else
    PROXY_SAN="DNS:${PROXY_SAN_VALUE}"
fi

[[ "$INSTALL_PATH" =~ ^/([A-Za-z0-9_-][A-Za-z0-9_.-]*/)*[A-Za-z0-9_-][A-Za-z0-9_.-]*$ ]] || die "invalid install_path"
uri_component() { printf '%s' "$1" | jq -sRr @uri; }
nats_string() { printf '%s' "$1" | jq -sRr @json; }

NATS_HOST_PATTERN='([[:alnum:].-]+|\[[[:xdigit:]:.]+\])'
if [ "$PACKAGE_VERSION" = 2 ]; then
    for p in nats_leaf_url nats_leaf_username nats_leaf_password nats_source_domain nats_bucket nats_installer_username nats_installer_password; do
        [ -n "$(get "$p")" ] || die "missing $p"
    done
    NATS_LEAF_URL=$(get nats_leaf_url)
    NATS_SOURCE_DOMAIN=$(get nats_source_domain)
    NATS_BUCKET=$(get nats_bucket)
    INSTALLER_USER=$(get nats_installer_username)
    if [[ ! "$NATS_LEAF_URL" =~ ^tls://$NATS_HOST_PATTERN:([0-9]{1,5})$ ]]; then
        die "invalid nats_leaf_url"
    fi
    leaf_port=${BASH_REMATCH[2]}
    (( 10#$leaf_port > 0 && 10#$leaf_port <= 65535 )) || die "invalid nats_leaf_url"
    [[ "$NATS_SOURCE_DOMAIN" =~ ^[A-Za-z0-9_-]+$ ]] || die "invalid nats_source_domain"
    [[ "$NATS_BUCKET" =~ ^[A-Za-z0-9_-]+$ ]] || die "invalid nats_bucket"
    if [[ "$INSTALLER_USER" == "$NATS_USER" || "$INSTALLER_USER" == "$MONITOR_USER" || "$INSTALLER_USER" == "$APM_NATS_USER" ]]; then
        die "conflicting nats_installer_username"
    fi
    REMOTE_NATS_URL="tls://$(uri_component "$(get nats_leaf_username)"):$(uri_component "$(get nats_leaf_password)")@${NATS_LEAF_URL#tls://}"
else
    # Old Server sends a TLS client endpoint and uses certificate-only Leafnode auth.
    # Preserve its endpoint and namespace while the hub is still on the legacy deployment.
    NATS_ENDPOINT=$(get nats_url)
    if [[ ! "${NATS_ENDPOINT#*://}" =~ ^$NATS_HOST_PATTERN(:([0-9]{1,5}))?$ ]]; then
        die "invalid nats_url"
    fi
    leaf_port=${BASH_REMATCH[3]:-4222}
    (( 10#$leaf_port > 0 && 10#$leaf_port <= 65535 )) || die "invalid nats_url"
    REMOTE_NATS_URL="tls://${BASH_REMATCH[1]}:$leaf_port"
    NATS_SOURCE_DOMAIN=bklite
    NATS_BUCKET=bklite
fi

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

cp -r "$PROXY_DIR"/* "$WORK/"
mkdir -p "$WORK/conf/certs" "$WORK/conf/traefik/certs"

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

export REMOTE_NATS_URL
export NATS_MONITOR_USERNAME_JSON=$(nats_string "$MONITOR_USER")
export NATS_MONITOR_PASSWORD_JSON=$(nats_string "$MONITOR_PASS")
export NATS_ADMIN_USERNAME_JSON=$(nats_string "$NATS_USER")
export NATS_ADMIN_PASSWORD_JSON=$(nats_string "$NATS_PASS")
export NATS_APM_USERNAME_JSON=$(nats_string "$APM_NATS_USER")
export NATS_APM_PASSWORD_JSON=$(nats_string "$APM_NATS_PASS")
export NATS_OBJECT_STREAM="OBJ_${NATS_BUCKET}"
NATS_INSTALLER_USER_BLOCK=
if [ "$PACKAGE_VERSION" = 2 ]; then
    export NATS_INSTALLER_USERNAME_JSON=$(nats_string "$INSTALLER_USER")
    export NATS_INSTALLER_PASSWORD_JSON=$(nats_string "$(get nats_installer_password)")
    NATS_INSTALLER_USER_BLOCK=$(envsubst '${NATS_INSTALLER_USERNAME_JSON} ${NATS_INSTALLER_PASSWORD_JSON} ${NATS_OBJECT_STREAM}' \
        < "$WORK/conf/nats/installer-user.conf.template")
fi
export NATS_INSTALLER_USER_BLOCK
envsubst '${ZONE_ID} ${REMOTE_NATS_URL} ${NATS_ADMIN_USERNAME_JSON} ${NATS_ADMIN_PASSWORD_JSON} ${NATS_MONITOR_USERNAME_JSON} ${NATS_MONITOR_PASSWORD_JSON} ${NATS_APM_USERNAME_JSON} ${NATS_APM_PASSWORD_JSON} ${NATS_INSTALLER_USER_BLOCK}' \
    < "$WORK/conf/nats/nats.conf.template" > "$WORK/conf/nats/nats.conf"
jq --arg stream "$NATS_OBJECT_STREAM" --arg api "\$JS.$NATS_SOURCE_DOMAIN.API" \
    '.name = $stream | .mirror.name = $stream | .mirror.external.api = $api' \
    "$PROXY_DIR/conf/nats/jetstream.json" > "$WORK/conf/nats/jetstream.json"

rm -f "$WORK/proxy.cnf" "$WORK/proxy.csr" "$WORK/env.template" "$WORK/conf/nats/nats.conf.template" "$WORK/conf/nats/installer-user.conf.template"

ARCHIVE=$(tar -czf - -C "$WORK" . | base64 | tr -d '\n')

INSTALL_SCRIPT=$(
    printf '#!/bin/bash\nset -euo pipefail\numask 077\nINSTALL_PATH="%s"\nARCHIVE="%s"\n' "$INSTALL_PATH" "$ARCHIVE"
    cat "$SCRIPT_DIR/install-proxy-payload.sh"
)

# The script contains a private key and credentials. Pass it on stdin, not as
# a process argument, and let webhookd return it to the authorized caller.
printf '%s' "$INSTALL_SCRIPT" | jq -Rs --arg id "$NODE_ID" --argjson version "$PACKAGE_VERSION" \
    '{status:"success",id:$id,message:"ok",install_script:.} | if $version == 2 then .proxy_package_version = $version else . end'

#!/bin/bash

# 检查NATS_URLS协议头，是tls时启用TLS
if [[ "$NATS_URLS" == tls:* ]]; then
    cat > /opt/config.yml << EOF
nats_urls: "${NATS_URLS}"
nats_instanceId: "${NATS_INSTANCE_ID}"

tls_enabled: "true"
tls_skip_verify: "false"
tls_ca_file: "${NATS_CA_FILE}"
EOF
else
    cat > /opt/config.yml << EOF
nats_urls: "${NATS_URLS}"
nats_instanceId: "${NATS_INSTANCE_ID}"
EOF
fi


# 启动程序
supervisord -n
#!/bin/bash

cat > /opt/config.yml << EOF
nats_servers: "${NATS_SERVERS}"
nats_username: "${NATS_USERNAME}"
nats_password: "${NATS_PASSWORD}"
nats_protocol: "${NATS_PROTOCOL}"
nats_tls_ca_file: "${NATS_TLS_CA_FILE}"
nats_instance_id: "${NATS_INSTANCE_ID}"
nats_conn_timeout: ${NATS_CONNECT_TIMEOUT}
EOF

supervisord -n

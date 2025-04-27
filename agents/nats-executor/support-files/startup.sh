#!/bin/bash

# 从环境变量生成配置文件
cat > /opt/config.yml << EOF
nats_urls: "${NATS_URLS}"
nats_instanceId: "${NATS_INSTANCE_ID}"
EOF

# 启动程序
/opt/nats-executor --config /opt/config.yml
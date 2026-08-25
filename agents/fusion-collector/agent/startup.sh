#!/bin/bash

sed -i "s|__SERVER__URL__|$SERVER_URL|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SERVER__API__TOKEN__|$SERVER_API_TOKEN|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SIDECAR__ZONE__|$SIDECAR_ZONE|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SIDECAR__GROUP__|$SIDECAR_GROUP|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SIDECAR__NODE__NAME__|$SIDECAR_NODE_NAME|g" /opt/fusion-collectors/sidecar.yml

echo $SIDECAR_NODEID > /opt/fusion-collectors/node-id
# Vector 0.34 unix_datagram 绑定前不会删除残留 sock；docker restart 会保留 /tmp。
rm -f /tmp/snmp_trap.sock
supervisord -n
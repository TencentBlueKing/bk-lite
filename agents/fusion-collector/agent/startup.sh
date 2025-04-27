#!/bin/bash

sed -i "s|__SERVER__URL__|$SERVER_URL|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SERVER__API__TOKEN__|$SERVER_API_TOKEN|g" /opt/fusion-collectors/sidecar.yml

/opt/fusion-collectors/collector-sidecar -c /opt/fusion-collectors/sidecar.yml
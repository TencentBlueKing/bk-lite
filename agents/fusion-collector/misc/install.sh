#!/bin/bash

# 确保脚本以 root 权限运行
if [ "$(id -u)" -ne 0; then
    echo "请使用 root 权限运行此脚本"
    exit 1
fi

# 检查参数
if [ $# -ne 2 ]; then
    echo "用法: $0 {server_url} {server_api_token}"
    exit 1
fi

SERVER_URL=$1
SERVER_API_TOKEN=$2

echo "开始安装 Fusion Collector Sidecar 服务..."

# 创建必要的目录
mkdir -p /opt/fusion-collectors/bin
mkdir -p /opt/fusion-collectors/cache
mkdir -p /opt/fusion-collectors/log
mkdir -p /opt/fusion-collectors/generated

# 复制并修改配置文件
sed -i "s|__SERVER__URL__|$SERVER_URL|g" /opt/fusion-collectors/sidecar.yml
sed -i "s|__SERVER__API__TOKEN__|$SERVER_API_TOKEN|g" /opt/fusion-collectors/sidecar.yml

# 复制服务文件到 systemd 目录
cp -Rf "./sidecar.service" /etc/systemd/system/

# 重新加载 systemd 配置
systemctl daemon-reload

systemctl enable --now sidecar.service
echo "服务已设置为开机自启动"

echo "安装完成"
exit 0

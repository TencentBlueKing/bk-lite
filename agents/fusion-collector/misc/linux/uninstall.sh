#!/bin/bash

# 确保脚本以 root 权限运行
if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 权限运行此脚本"
    exit 1
fi

echo "开始卸载 Fusion Collector Sidecar 服务..."

# 停止服务
systemctl stop sidecar.service
echo "服务已停止"

# 禁用服务自启动
systemctl disable sidecar.service
echo "服务已禁用自启动"

# 删除服务文件
rm -f /etc/systemd/system/sidecar.service
echo "服务文件已删除"

# 重新加载 systemd 配置
systemctl daemon-reload
systemctl reset-failed

echo "Fusion Collector Sidecar 服务卸载完成"
exit 0

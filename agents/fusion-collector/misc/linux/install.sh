#!/bin/bash
#
# Fusion Collector Sidecar 安装脚本
# 用途: 安装和配置 Fusion Collector Sidecar 服务
#

# 显示使用方法
show_usage() {
    echo "用法: $0 {server_url} {server_api_token} {zone} {teams} [node_name] [node_id]"
    echo ""
    echo "参数说明:"
    echo "  server_url       - 服务器URL"
    echo "  server_api_token - 服务器API令牌"
    echo "  zone             - 云区域"
    echo "  teams           - 分组信息"
    echo "  node_name        - 节点名称 (可选)"
    echo "  node_id          - 节点ID (可选)"
    exit 1
}

# 检查root权限
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "错误: 请使用 root 权限运行此脚本"
        exit 1
    fi
}

# 检查参数数量
check_args() {
    if [ $# -lt 4 ] || [ $# -gt 6 ]; then
        show_usage
    fi
}

# 安装服务
install_service() {
    echo "开始安装 Fusion Collector Sidecar 服务..."

    # 替换配置文件中的占位符
    sed -i "s|__SERVER__URL__|$SERVER_URL|g" /opt/fusion-collectors/sidecar.yml
    sed -i "s|__SERVER__API__TOKEN__|$SERVER_API_TOKEN|g" /opt/fusion-collectors/sidecar.yml
    sed -i "s|__TAGS__|\"cloud:$ZONE\", \"group:$TEAMS\"|g" /opt/fusion-collectors/sidecar.yml
    sed -i "s|__NODE__NAME__|$NODE_NAME|g" /opt/fusion-collectors/sidecar.yml

    # 拷贝服务文件并启用
    cp -f "./sidecar.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable --now sidecar.service

    if [ $? -eq 0 ]; then
        echo "服务已成功启动并设置为开机自启动"
    else
        echo "警告: 服务启动过程中出现问题，请检查系统日志"
    fi
}

# 主函数
main() {
    # 检查权限和参数
    check_root
    check_args "$@"

    # 解析参数
    SERVER_URL=$1
    SERVER_API_TOKEN=$2
    ZONE=$3
    TEAMS=$4
    NODE_NAME=""
    NODE_ID=""

    # 处理可选参数
    if [ $# -ge 5 ]; then
        NODE_NAME=$5
    fi

    if [ $# -eq 6 ]; then
        NODE_ID=$6
        echo "$NODE_ID" > ./node-id
        echo "Node ID 已写入到 ./node-id 文件"
    fi

    # 安装服务
    install_service

    echo "安装完成"
    exit 0
}

# 执行主函数
main "$@"
#!/bin/sh
#
# Fusion Collector Sidecar 安装脚本
# 用途: 安装和配置 Fusion Collector Sidecar 服务
#

# 显示使用方法
show_usage() {
    echo "用法: $0 {server_url} {server_api_token} {zone} {teams} [node_name] [node_id] [cpu_architecture]"
    echo ""
    echo "参数说明:"
    echo "  server_url       - 服务器URL"
    echo "  server_api_token - 服务器API令牌；setup-worker 可通过 BK_LITE_SERVER_API_TOKEN_FILE 安全传入"
    echo "  zone             - 云区域"
    echo "  teams           - 分组信息"
    echo "  node_name        - 节点名称 (可选)"
    echo "  node_id          - 节点ID (可选)"
    echo "  cpu_architecture - CPU架构 (可选)"
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
    if [ $# -lt 4 ] || [ $# -gt 7 ]; then
        show_usage
    fi
}

load_server_api_token() {
    token_arg=$1

    if [ -n "${BK_LITE_SERVER_API_TOKEN_FILE:-}" ]; then
        if [ ! -r "$BK_LITE_SERVER_API_TOKEN_FILE" ]; then
            echo "错误: 无法读取 server_api_token 文件"
            exit 1
        fi
        SERVER_API_TOKEN=$(cat "$BK_LITE_SERVER_API_TOKEN_FILE")
        rm -f -- "$BK_LITE_SERVER_API_TOKEN_FILE"
        return
    fi

    SERVER_API_TOKEN=$token_arg
}

# 安装服务
install_service() {
    echo "开始安装 Fusion Collector Sidecar 服务..."

    service_source=""

    if [ -f "./bk-sidecar.service" ]; then
        service_source="./bk-sidecar.service"
    elif [ -f "./sidecar.service" ]; then
        service_source="./sidecar.service"
    else
        echo "错误: 未找到 systemd 服务文件 (bk-sidecar.service / sidecar.service)"
        exit 1
    fi

    escape_sed_replacement() {
        printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
    }

    ESCAPED_SERVER_URL=$(escape_sed_replacement "$SERVER_URL")
    ESCAPED_SERVER_API_TOKEN=$(escape_sed_replacement "$SERVER_API_TOKEN")
    ESCAPED_ZONE=$(escape_sed_replacement "$ZONE")
    ESCAPED_TEAMS=$(escape_sed_replacement "$TEAMS")
    ESCAPED_NODE_NAME=$(escape_sed_replacement "$NODE_NAME")
    ESCAPED_CPU_ARCHITECTURE=$(escape_sed_replacement "$CPU_ARCHITECTURE")

    # 替换配置文件中的占位符
    sed -i "s|__SERVER__URL__|$ESCAPED_SERVER_URL|g" /opt/fusion-collectors/sidecar.yml
    sed -i "s|__SERVER__API__TOKEN__|$ESCAPED_SERVER_API_TOKEN|g" /opt/fusion-collectors/sidecar.yml
    TAGS="\"zone:$ESCAPED_ZONE\", \"group:$ESCAPED_TEAMS\""
    if [ -n "$CPU_ARCHITECTURE" ]; then
        TAGS="$TAGS, \"cpu_architecture:$ESCAPED_CPU_ARCHITECTURE\""
    fi
    sed -i "s|__TAGS__|$TAGS|g" /opt/fusion-collectors/sidecar.yml
    sed -i "s|__NODE__NAME__|$ESCAPED_NODE_NAME|g" /opt/fusion-collectors/sidecar.yml

    # 拷贝服务文件并启用
    systemctl stop sidecar.service >/dev/null 2>&1 || true
    systemctl disable sidecar.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/sidecar.service

    cp -f "$service_source" /etc/systemd/system/bk-sidecar.service
    systemctl daemon-reload
    systemctl enable --now bk-sidecar.service

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
    load_server_api_token "$2"
    ZONE=$3
    TEAMS=$4
    NODE_NAME=""
    NODE_ID=""
    CPU_ARCHITECTURE=""

    # 处理可选参数
    if [ $# -ge 5 ]; then
        NODE_NAME=$5
    fi

    if [ $# -ge 6 ]; then
        NODE_ID=$6
        echo "$NODE_ID" > ./node-id
        echo "Node ID 已写入到 ./node-id 文件"
    fi

    if [ $# -ge 7 ]; then
        CPU_ARCHITECTURE=$7
    fi

    # 安装服务
    install_service

    echo "安装完成"
    exit 0
}

# 执行主函数
main "$@"

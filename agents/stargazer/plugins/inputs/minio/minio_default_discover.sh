#!/bin/bash
# MinIO 对象存储自动发现采集脚本（Beta）
# 输出：每个 minio server 进程一行 JSON，字段对齐 CMDB minio 模型
bk_host_innerip=$(hostname -I | awk '{print $1}')

Get_Minio_Version() {
    local exe="$1"
    local v
    v=$("$exe" --version 2>/dev/null | head -1 | grep -oE 'RELEASE\.[0-9TZ:-]+' | head -1)
    if [ -z "$v" ]; then
        v=$("$exe" --version 2>/dev/null | head -1 | awk '{print $3}')
    fi
    [ -z "$v" ] && v="unknown"
    echo "$v"
}

Cover_Minio() {
    # 匹配 minio server 进程
    local pid_arr
    pid_arr=$(ps -ef | grep "[m]inio server" | awk '{print $2}')
    for pid in ${pid_arr[@]}; do
        local exe_path cmdline
        exe_path=$(readlink -f /proc/$pid/exe 2>/dev/null)
        [ -z "$exe_path" ] && exe_path=$(ps -p "$pid" -o comm= 2>/dev/null)
        cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
        [ -z "$cmdline" ] && cmdline=$(ps -p "$pid" -o args= 2>/dev/null)

        local version
        version=$(Get_Minio_Version "$exe_path")

        # API 端口（--address :9000）
        local port
        port=$(echo "$cmdline" | grep -oP '(?<=--address\s)\S+' | awk -F: '{print $NF}')
        [ -z "$port" ] && port="9000"

        # 控制台端口（--console-address :9001）
        local console_port
        console_port=$(echo "$cmdline" | grep -oP '(?<=--console-address\s)\S+' | awk -F: '{print $NF}')

        # 配置/环境文件
        local conf_path="/etc/default/minio"
        [ -f /etc/minio/minio.conf ] && conf_path="/etc/minio/minio.conf"

        # 数据目录：优先 MINIO_VOLUMES 环境文件，其次从命令行尾部参数提取
        local volumes=""
        if [ -f "$conf_path" ]; then
            volumes=$(grep -E '^MINIO_VOLUMES' "$conf_path" | head -1 | cut -d= -f2- | tr -d '"')
        fi
        if [ -z "$volumes" ]; then
            volumes=$(echo "$cmdline" | sed -E 's/.*minio server//' | grep -oE '(/[^ ]+|https?://[^ ]+)' | tr '\n' ',' | sed 's/,$//')
        fi

        # 区域
        local region=""
        if [ -f "$conf_path" ]; then
            region=$(grep -E '^MINIO_REGION(_NAME)?=|^MINIO_SITE_REGION=' "$conf_path" | head -1 | cut -d= -f2- | tr -d '"')
        fi

        # 部署模式推断
        local deploy_mode="standalone"
        if echo "$volumes" | grep -qE 'https?://|\{.*\.\.\.'; then
            deploy_mode="distributed"
        elif [ "$(echo "$volumes" | tr ',' '\n' | grep -c .)" -gt 1 ]; then
            deploy_mode="erasure"
        fi

        local inst_name="$bk_host_innerip-minio-$port"
        local json_template='{ "bk_inst_name": "%s", "bk_obj_id": "minio", "ip_addr": "%s", "port": "%s", "console_port": "%s", "version": "%s", "bin_path": "%s", "data_path": "%s", "conf_path": "%s", "deploy_mode": "%s", "region": "%s", "start_args": "%s" }'
        printf "$json_template" "$inst_name" "$bk_host_innerip" "$port" "$console_port" "$version" "$exe_path" "$volumes" "$conf_path" "$deploy_mode" "$region" "$cmdline"
        echo ""
    done
}

Cover_Minio

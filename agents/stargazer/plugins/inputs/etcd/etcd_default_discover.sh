#!/bin/bash

# 注意：脚本 stdout 会被 stargazer 解析为 JSON。
# 为避免“stderr 噪声 + 多条非 JSON 文本”导致解析失败，这里尽量：
# 1) 不输出任何调试信息到 stdout（必要时输出到 stderr 或丢弃）
# 2) 跳过已退出/不合法 PID（/proc 可能瞬时消失）
# 3) 仅输出单行 JSON（每个实例一行）

host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')

get_etcd_details() {
    pid=$1
    # /proc 下的内容可能瞬时消失（进程退出/重启），遇到异常直接跳过
    if [ ! -e "/proc/$pid/exe" ] || [ ! -e "/proc/$pid/cmdline" ]; then
        return 0
    fi

    etcd_exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
    if [ -z "$etcd_exe" ] || [ ! -x "$etcd_exe" ]; then
        return 0
    fi

    install_path=$(dirname "$etcd_exe" 2>/dev/null)
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    if [ -z "$cmdline" ]; then
        return 0
    fi

    config_file=$(echo "$cmdline" | grep -oP '(?<=--config-file=)\S+' 2>/dev/null | head -1)
    data_dir=$(echo "$cmdline" | grep -oP '(?<=--data-dir=)\S+' 2>/dev/null | head -1)
    listen_client_urls=$(echo "$cmdline" | grep -oP '(?<=--listen-client-urls=)\S+' 2>/dev/null | head -1)
    listen_peer_urls=$(echo "$cmdline" | grep -oP '(?<=--listen-peer-urls=)\S+' 2>/dev/null | head -1)

    version=$(
        "$etcd_exe" --version 2>/dev/null | grep -oP '(?<=etcd Version: )\S+' | head -1
    )

    if [ -z "$data_dir" ] && [ -n "$config_file" ] && [ -f "$config_file" ]; then
        data_dir=$(grep -oP '(?<=data-dir: )\S+' "$config_file" 2>/dev/null | head -1)
    fi
    if [ -z "$data_dir" ]; then
      # 默认值
        data_dir="default.etcd"
    fi

    if [ -z "$listen_client_urls" ] && [ -n "$config_file" ] && [ -f "$config_file" ]; then
        listen_client_urls=$(grep -oP '(?<=listen-client-urls: )\S+' "$config_file" 2>/dev/null | head -1)
    fi
    if [ -z "$listen_client_urls" ]; then
      # 默认值
        listen_client_urls="http://localhost:2379"
    fi

    if [ -z "$listen_peer_urls" ] && [ -n "$config_file" ] && [ -f "$config_file" ]; then
        listen_peer_urls=$(grep -oP '(?<=listen-peer-urls: )\S+' "$config_file" 2>/dev/null | head -1)
    fi
    if [ -z "$listen_peer_urls" ]; then
      # 默认值
        listen_peer_urls="http://localhost:2380"
    fi

    client_port=$(echo "$listen_client_urls" | grep -oP ':\K\d+' 2>/dev/null | head -1)
    peer_port=$(echo "$listen_peer_urls" | grep -oP ':\K\d+' 2>/dev/null | head -1)

    # 兜底：端口缺失时用默认值，避免 inst_name 为空
    if [ -z "$client_port" ]; then
        client_port="2379"
    fi
    if [ -z "$peer_port" ]; then
        peer_port="2380"
    fi

    json_template='{ "inst_name": "%s-etcd-%s", "obj_id": "etcd", "ip_addr": "%s", "port": "%s", "install_path": "%s", "version": "%s", "data_dir": "%s", "conf_file_path": "%s", "peer_port": "%s" }'
    printf "$json_template\n" "$host_innerip" "$client_port" "$host_innerip" "$client_port" "$install_path" "$version" "$data_dir" "$config_file" "$peer_port"
}

get_etcd_pids() {
    # 优先精确匹配 etcd 进程名，避免把 etcdctl/脚本自身/其它包含 etcd 字符串的进程误判进来
    if command -v pgrep >/dev/null 2>&1; then
        pgrep -x etcd 2>/dev/null
        return 0
    fi

    ps -ef 2>/dev/null | grep -w '[e]tcd' | awk '{print $2}'
}

main() {
    pids=$(get_etcd_pids)
    if [ -z "$pids" ]; then
        # 按“发现不到服务时不报错”的语义：不输出任何实例即可。
        # 由上层合并逻辑决定是否需要生成空的 success 记录。
        exit 0
    fi
    for pid in $pids; do
        get_etcd_details "$pid"
    done
}

main

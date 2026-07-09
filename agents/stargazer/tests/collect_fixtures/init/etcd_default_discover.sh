#!/bin/bash
set -e  # 遇到错误立即退出

host_innerip=$(hostname -I | awk '{print $1}')

get_etcd_details() {
    pid=$1
    etcd_exe=$(readlink -f /proc/$pid/exe)
    install_path=$(dirname $etcd_exe)
    cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
    config_file=$(echo $cmdline | grep -oP '(?<=--config-file=)\S+')
    data_dir=$(echo $cmdline | grep -oP '(?<=--data-dir=)\S+')
    listen_client_urls=$(echo $cmdline | grep -oP '(?<=--listen-client-urls=)\S+')
    listen_peer_urls=$(echo $cmdline | grep -oP '(?<=--listen-peer-urls=)\S+')
    version=$($etcd_exe --version | grep -oP '(?<=etcd Version: )\S+')

    if [ -z "$data_dir" ] && [ ! -z "$config_file" ]; then
        data_dir=$(grep -oP '(?<=data-dir: )\S+' $config_file)
    fi
    if [ -z "$data_dir" ]; then
      # 默认值
        data_dir="default.etcd"
    fi

    if [ -z "$listen_client_urls" ] && [ ! -z "$config_file" ]; then
        listen_client_urls=$(grep -oP '(?<=listen-client-urls: )\S+' $config_file)
    fi
    if [ -z "$listen_client_urls" ]; then
      # 默认值
        listen_client_urls="http://localhost:2379"
    fi

    if [ -z "$listen_peer_urls" ] && [ ! -z "$config_file" ]; then
        listen_peer_urls=$(grep -oP '(?<=listen-peer-urls: )\S+' $config_file)
    fi
    if [ -z "$listen_peer_urls" ]; then
      # 默认值
        listen_peer_urls="http://localhost:2380"
    fi

    client_port=$(echo $listen_client_urls | grep -oP ':\K\d+' | head -1)
    peer_port=$(echo $listen_peer_urls | grep -oP ':\K\d+' | head -1)




    json_template='{ "inst_name": "%s-etcd-%s", "obj_id": "etcd", "ip_addr": "%s", "port": "%s", "install_path": "%s", "version": "%s", "data_dir": "%s", "conf_file_path": "%s", "peer_port": "%s" }'
    json_string=$(printf "$json_template" "$host_innerip" "$client_port" "$host_innerip" "$client_port" "$install_path" "$version" "$data_dir" "$config_file" "$peer_port")
    echo "$json_string"
}

get_etcd_pids() {
    pids=$(ps -ef | grep -v 'grep' | grep 'etcd' | awk '{print $2}')
    echo $pids
}

main() {
    pids=$(get_etcd_pids)
    if [ -z "$pids" ]; then
        echo '{}'
        exit 1
    fi
    for pid in $pids; do
        echo "$(get_etcd_details $pid)"
    done
}

main

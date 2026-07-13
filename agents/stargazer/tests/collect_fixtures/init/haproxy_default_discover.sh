#!/bin/bash
# Haproxy 采集 wrapper（G3.7,2026-07-08）
# -----------------------------------------------------------------------------
# 真实采集逻辑:复用 plugins/inputs/haproxy/haproxy_default_discover.sh(70 行)。
# 本副本修了 bk_host_innerip 模板替换 bug(同 memcached G3.5 / openresty G3.6 模式):
# 上游写死 "{{bk_host_innerip}}",实际 runner 不替换。改成 hostname 实际获取。
# 同步策略:与 plugins/inputs/haproxy/haproxy_default_discover.sh 保持同步,
# 头部 patch 注释记录本次本地修改。

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

getoutput() {
    cmd=$1
    eval "$cmd"
}

get_process() {
    pids=$(pgrep -x "haproxy")
    for pid in $pids; do
        cmds=$(ps -p $pid -o args=)
        if [[ "$cmds" == *"-f"* ]]; then
            echo $cmds
            return
        fi
    done
    echo ""
}

get_version() {
    binfile=$1
    out=$(getoutput "$binfile -v")
    version=$(echo "$out" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
    echo $version
}

get_attribute() {
    section=$1
    attribute=$2
    config_file=$3
    awk -v section="$section" -v attribute="$attribute" '
    BEGIN { in_section=0 }
    $1 == section { in_section=1; next }
    in_section && $1 == attribute { print $2; exit }
    in_section && $1 == "defaults" { in_section=0 }
    ' "$config_file"
}

str_join_sep() {
    local IFS="$1"
    shift
    echo "$*"
}

get_haproxy_listen_port() {
    haproxy_listen_port=$(netstat -antp | grep haproxy | grep -v tcp6 | awk '{print $4}' | awk -F: '{print $2}' | sort | uniq)
    echo $(str_join_sep "&" $haproxy_listen_port)
}

discovery() {
    process_info=$(get_process)
    [ -z "$process_info" ] && echo "{}" && exit 0
    binfile=$(echo $process_info | awk '{print $1}')
    config=$(echo $process_info | awk -F '-f ' '{print $2}' | awk '{print $1}')
    install_path=$(echo $binfile | sed 's/\/sbin\/haproxy$//')
    global_maxconn=$(get_attribute "global" "maxconn" "$config")
    global_pidfile=$(get_attribute "global" "pidfile" "$config")
    global_group_name=$(get_attribute "global" "group" "$config")
    global_user_name=$(get_attribute "global" "user" "$config")
    defaults_maxconn=$(get_attribute "defaults" "maxconn" "$config")
    defaults_mode=$(get_attribute "defaults" "mode" "$config")
    defaults_retries=$(get_attribute "defaults" "retries" "$config")
    front_ports=$(get_haproxy_listen_port)
    [ -z "$front_ports" ] && echo "{}" && exit 0
    bk_inst_name="$bk_host_innerip-haproxy-${front_ports}"
    printf '{"bk_inst_name":"%s","bk_obj_id":"haproxy","ip_addr":"%s","version":"%s","install_path":"%s","conf_file":"%s","global_maxconn":"%s","global_pidfile":"%s","global_group_name":"%s","global_user_name":"%s","defaults_maxconn":"%s","defaults_mode":"%s","defaults_retries":"%s","port":"%s"}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$(get_version "$binfile")" "$install_path" "$config" "$global_maxconn" "$global_pidfile" "$global_group_name" "$global_user_name" "$defaults_maxconn" "$defaults_mode" "$defaults_retries" "$front_ports"
}

discovery

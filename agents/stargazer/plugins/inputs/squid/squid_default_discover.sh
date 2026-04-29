#!/bin/bash
bk_host_innerip={{bk_host_innerip}}

get_squid_details() {
    pid=$1
    squid_exe=$(readlink -f /proc/$pid/exe)
    install_path=$(dirname "$squid_exe")
    cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
    config_file=$(echo "$cmdline" | grep -oP '(?<=-f )\S+' || echo "/etc/squid/squid.conf")
    version=$($squid_exe -v | grep -oP '(?<=Squid Cache: Version )\S+')
    http_port=$(grep -oP 'http_port\s+\K\S+' "$config_file" | head -1)
    http_port=${http_port:-"3128"}
    cache_dir=$(grep -oP 'cache_dir\s+\K\S+' "$config_file" | head -1)
    access_log=$(grep -oP 'access_log\s+\K\S+' "$config_file" | head -1)
    error_log=$(grep -oP 'cache_log\s+\K\S+' "$config_file" | head -1)
    visible_hostname=$(grep -oP 'visible_hostname\s+\K\S+' "$config_file" | head -1)
    printf '{"bk_inst_name":"%s-squid-%s","bk_obj_id":"squid","ip_addr":"%s","port":"%s","install_path":"%s","version":"%s","config_file_path":"%s","cache_dir":"%s","access_log":"%s","error_log":"%s","visible_hostname":"%s"}\n' \
        "$bk_host_innerip" "$http_port" "$bk_host_innerip" "$http_port" "$install_path" "$version" "$config_file" "$cache_dir" "$access_log" "$error_log" "$visible_hostname"
}

get_squid_pids() {
    ps -eo pid,ppid,comm | grep 'squid' | grep -v 'grep' | awk '$2 == 1 {print $1}'
}

main() {
    pids=$(get_squid_pids)
    [ -z "$pids" ] && echo "{}" && exit 0
    for pid in $pids; do
        get_squid_details $pid
    done
}

main

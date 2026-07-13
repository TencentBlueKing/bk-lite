#!/bin/bash
# Memcached 采集 wrapper（G3.5,2026-07-08）
# -----------------------------------------------------------------------------
# 真实采集逻辑:复用 plugins/inputs/memcached/memcached_default_discover.sh(35 行)。
# 本副本仅修了 2 个上游已知 bug,以便 fixture 工具真实跑通:
# 1. bk_host_innerip 模板替换:上游写死 "{{bk_host_innerip}}",假设 runner 替换
#    (实际没替换),改成 `hostname -I` 实际获取(同 nginx/minio 副本模式)
# 2. version 检测:上游 `memcached -V` 输出含 "memcached X.Y.Z" 但 grep -oP
#    '(?<=memcached )' 在 alpine busybox grep 上没问题,但 ubuntu 22.04 grep -P
#    也支持。先保持原样,跑通后看实际 JSON。
# 同步策略:与 plugins/inputs/memcached/memcached_default_discover.sh 保持同步,
# 头部 patch 注释记录本次本地修改。

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

re_search() {
    pattern=$1
    string=$2
    result=$(echo "$string" | grep -oP "$pattern")
    echo "$result"
}

discover_memcached() {
    memcached_pids=$(ps -ef | grep 'memcached' | grep -v grep | awk '{print $2}')
    if [ -z "$memcached_pids" ]; then
        echo "{}"
        exit 0
    fi
    for pid in $memcached_pids; do
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        port=$(re_search '(?<=-p )\d+' "$cmdline")
        maxconn=$(re_search '(?<=-c )\d+' "$cmdline")
        cachesize=$(re_search '(?<=-m )\d+' "$cmdline")
        user_name=$(ps -p $pid -o user=)
        exe_path=$(readlink -f /proc/$pid/exe)
        if [[ "$exe_path" == *"/bin/memcached" ]]; then
            install_path=$(echo "$exe_path" | sed 's/\/bin\/memcached//')
        else
            install_path=$(dirname "$exe_path")
        fi
        version=$($exe_path -V | grep -oP '(?<=memcached )\d+\.\d+\.\d+')
        bk_inst_name="$bk_host_innerip-memcached-${port}"
        printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"memcached","port":"%s","version":"%s","maxconn":"%s","cachesize":"%s","user_name":"%s","install_path":"%s"}\n' \
            "$bk_inst_name" "$bk_host_innerip" "$port" "$version" "$maxconn" "$cachesize" "$user_name" "$install_path"
    done
}

discover_memcached

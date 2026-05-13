#!/bin/bash

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
        bk_inst_name="{{bk_host_innerip}}-memcached-${port}"
        printf '{"bk_inst_name":"%s","ip_addr":"{{bk_host_innerip}}","bk_obj_id":"memcached","port":"%s","version":"%s","maxconn":"%s","cachesize":"%s","user_name":"%s","install_path":"%s"}\n' \
            "$bk_inst_name" "$port" "$version" "$maxconn" "$cachesize" "$user_name" "$install_path"
    done
}

discover_memcached

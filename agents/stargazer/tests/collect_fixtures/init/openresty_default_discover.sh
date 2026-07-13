#!/bin/bash
# Openresty 采集 wrapper（G3.6,2026-07-08）
# -----------------------------------------------------------------------------
# 真实采集逻辑:复用 plugins/inputs/openresty/openresty_default_discover.sh(57 行)。
# 本副本修了 bk_host_innerip 模板替换 bug(同 memcached G3.5 模式):上游写死
# `bk_host_innerip={{bk_host_innerip}}`,实际 runner 不替换。改成 hostname 实际获取。
# 同步策略:与 plugins/inputs/openresty/openresty_default_discover.sh 保持同步,
# 头部 patch 注释记录本次本地修改。

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

Get_Port_Join_Str(){
    port_arr_str=$(netstat -ntlp | grep "$1" | awk '{print $4}' | awk -F ':' '{print $NF}' | sed 's/ *$//g' | sed 's/^ *//g' | sort | uniq | tr '\n' '&')
    port_str="${port_arr_str%&}"
}

Get_Openresty_Pid(){
    i=0
    openresty_pid=()
    pid_arr=$(ps -ef  | grep "nginx" | grep -v grep | grep 'master process' |awk '{print $2}')
    for pid in ${pid_arr[@]}; do
        port_str=$(netstat -ntlp | grep -w $pid)
        [ -z "$port_str" ] && continue
        is_openresty=$(echo $(readlink /proc/$pid/exe) |grep -i openresty)
        [ -z "$is_openresty" ] && continue
        openresty_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Get_Openresty_Version(){
    openresty_version=$("$1" -v 2>&1 | grep "nginx version" | awk -F'/' '{print $2}' | awk '{print $1}')
    echo "$openresty_version"
}

Get_DocumentRoot(){
    document_root=$(grep -i 'root' "$1" | awk '{print $2}' | sed 's/;$//')
    echo "$document_root"
}

Cover_Openresty(){
    inst_name_array=()
    Get_Openresty_Pid
    for pid in "${openresty_pid[@]}"; do
        Get_Port_Join_Str "$pid"
        exe_path=$(readlink /proc/"$pid"/exe)
        [[ "${inst_name_array[*]}" =~ $bk_host_innerip-openresty-$port_str ]] && continue
        inst_name_array[${#inst_name_array[@]}]="$bk_host_innerip-openresty-$port_str"
        openresty_version=$(Get_Openresty_Version "$exe_path")
        install_path=$(dirname $(dirname "$exe_path"))
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        openresty_conf=$(echo "$cmdline" | grep -oP '(?<=-c\s)(\S+)')
        if [ -n "$openresty_conf" ] && [[ "$openresty_conf" != /* ]]; then
            openresty_conf="$install_path/$openresty_conf"
        elif [ -z "$openresty_conf" ]; then
            openresty_conf="$install_path/conf/nginx.conf"
        fi
        log_path=$(grep -i 'error_log' "$openresty_conf" | awk '{print $2}' | sed 's/;$//')
        doc_root=$(Get_DocumentRoot "$openresty_conf")
        printf '{"bk_inst_name":"%s-openresty-%s","bk_obj_id":"openresty","ip_addr":"%s","listen_port":"%s","openresty_path":"%s","version":"%s","log_path":"%s","config_path":"%s","doc_root":"%s"}\n' \
            "$bk_host_innerip" "$port_str" "$bk_host_innerip" "$port_str" "$exe_path" "$openresty_version" "$log_path" "$openresty_conf" "$doc_root"
    done
}

Cover_Openresty

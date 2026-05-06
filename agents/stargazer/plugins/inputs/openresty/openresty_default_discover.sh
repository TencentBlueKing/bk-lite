#!/bin/bash
bk_host_innerip={{bk_host_innerip}}

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

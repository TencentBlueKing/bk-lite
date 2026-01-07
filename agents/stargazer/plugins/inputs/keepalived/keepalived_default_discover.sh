#!/bin/bash

bk_host_innerip={{bk_host_innerip}}

re_search() {
    pattern=$1
    string=$2
    result=$(echo "$string" | grep -oP "$pattern")
    echo "$result"
}

discover_keepalived() {
    keepalived_pids=$(ps -ef | grep 'keepalived' | grep -v grep | awk '{print $2}')
    # 未启动keepalived服务直接打印空{}
    if [ ${#keepalived_pids} -eq 0 ]; then
      echo "{}"
      exit 0
    fi

    insts=()
    for pid in $keepalived_pids; do
        if [ -z "$pid" ]; then
            continue
        fi
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        config_file=$(re_search '(?<=-f )\\S+' "$cmdline")
        if [ -z "$config_file" ]; then
            config_file='/etc/keepalived/keepalived.conf'
        fi
        user_name=$(ps -p $pid -o user=)
        exe_path=$(readlink -f /proc/$pid/exe)

        if [[ "$exe_path" == *"/sbin/keepalived" ]]; then
            install_path=$(echo "$exe_path" | sed 's/\/sbin\/keepalived//')
        else
            install_path=$(dirname "$exe_path")
        fi

        version=$(eval $exe_path -v 2>&1 | grep -oP '(?<=Keepalived v)\d+\.\d+\.\d+')

        # Extract configuration details
        priority=$(grep -oP '(?<=priority )\d+' "$config_file")
        state=$(grep -oP '(?<=state )\w+' "$config_file")
        virtual_router_id=$(grep -oP '(?<=virtual_router_id )\d+' "$config_file")

        bk_inst_name="${bk_host_innerip}-keepalived-${virtual_router_id}"
        # 根据去重后的实例名，判断是否已经存在
        if [[ " ${insts[@]} " =~ " ${bk_inst_name} " ]]; then
            continue
        fi
        insts+=($bk_inst_name)

        bk_obj_id="keepalived"

        json_template='{"inst_name":"%s","ip_addr":"%s","bk_obj_id":"%s","version":"%s","priority":"%s","state":"%s","virtual_router_id":"%s","user_name":"%s","install_path":"%s","config_file":"%s"}'
        json_string=$(printf "$json_template" "$bk_inst_name" "$bk_host_innerip" "$bk_obj_id" "$version" "$priority" "$state" "$virtual_router_id" "$user_name" "$install_path" "$config_file")
        echo "$json_string"
    done
}

discover_keepalived
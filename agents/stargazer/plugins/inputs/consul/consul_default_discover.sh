#!/bin/bash

bk_host_innerip=""
if command -v ip >/dev/null 2>&1; then
    bk_host_innerip=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')
fi
if [ -z "$bk_host_innerip" ]; then
    bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

run_cmd() {
    cmd=$1
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

re_search() {
    pattern=$1
    string=$2
    result=$(echo "$string" | grep -oP "$pattern")
    echo "$result"
}

Get_Consul_Pid() {
    i=0
    consul_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep 'consul agent' | awk '{print $2}')
    for pid in ${pid_arr[@]}; do
        consul_pid[$i]=$pid
        ((i++))
    done
}

Get_Consul_Info() {
    Get_Consul_Pid

    for pid in ${consul_pid[@]}; do
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        consul_exe=$(readlink /proc/$pid/exe)
        if [ -z "$consul_exe" ]; then
            continue
        fi

        if [ -L "$consul_exe" ]; then
            real_path=$(readlink "$consul_exe")
            install_path=$(dirname "$real_path")
        else
            install_path=$(dirname "$consul_exe")
        fi

        consul_info=$(run_cmd "$consul_exe info")
        role=$(re_search '(?<=state = )[^}]+' "$consul_info")

        members=$(re_search '(?<=Address:)[^}]+' "$consul_info" | tr -d ' ')

        version=$(run_cmd "$consul_exe version" | grep -oP '(?<=Consul )\S+' | sed 's/v//')

        config_path=$(echo "$cmdline" | grep -oP '(?<=-config-file=)\S+' | tr '\n' ' ' | tr ' ' ':')
        if [ -z "$config_path" ]; then
            config_path=$(echo "$cmdline" | grep -oP '(?<=-config-dir=)\S+' | tr '\n' ' ' | tr ' ' ':')
        fi
        conf_path=${config_path%:}

        current_ip="$bk_host_innerip"

        http_port=$(echo "$cmdline" | grep -oP '(?<=-http-port=)\S+')
        if [ -z "$http_port" ]; then
            http_port=$(echo "$cmdline" | grep -oP '(?<=http=)\d+' | head -n 1)
        fi

        server_port=$(echo "$cmdline" | grep -oP '(?<=-server-port=)\S+')
        if [ -n "$http_port" ]; then
            server_port=$http_port
        fi
        if [ -z "$server_port" ]; then
            for member in ${members[@]}; do
                ip=$(echo "$member" | cut -d: -f1)
                port=$(echo "$member" | cut -d: -f2)
                if [ "$ip" = "$current_ip" ]; then
                    server_port=$port
                fi
            done
        fi
        if [ -z "$server_port" ]; then
            server_port=8500
        fi

        data_dir=$(echo "$cmdline" | grep -oP '(?<=-data-dir=)\S+')

        inst_name="$bk_host_innerip-consul-$server_port"

        json_template='{ "inst_name": "%s", "bk_obj_id": "consul", "ip_addr": "%s", "port": "%s", "install_path": "%s", "version": "%s", "data_dir": "%s", "conf_path": "%s", "role": "%s" }'
        json_string=$(printf "$json_template" "$inst_name" "$bk_host_innerip" "$server_port" "$install_path" "$version" "$data_dir" "$conf_path" "$role")
        echo "$json_string"
    done
}

Get_Consul_Info
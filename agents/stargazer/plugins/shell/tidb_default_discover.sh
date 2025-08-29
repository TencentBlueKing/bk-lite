#!/bin/bash

# Function to get config content
get_config_content() {
    cfg_path=$1
    declare -A ret
    while IFS= read -r line; do
        if [[ $line == \#* ]]; then
            continue
        fi
        if [[ $line == *=* ]]; then
            line=$(echo $line | sed 's/ *= */=/g')
            key=$(echo $line | cut -d '=' -f 1)
            value=$(echo $line | cut -d '=' -f 2-)
            ret[$key]=$value
        fi
    done < $cfg_path
    echo $(declare -p ret)
}

# Function to get TiDB version
get_tidb_version() {
    local install_path=$1
    echo $($install_path/bin/tidb-server -V | grep "Release Version" | awk '{print $3}')
}

# Function to get TiDB listener ports
get_listener_ports() {
    local listener_pid=$1
    local ports=()
    for net_connection in $(ss -lntp | grep $listener_pid | awk '{print $4}'); do
        local port=$(echo $net_connection | awk -F: '{print $NF}')
        ports+=("$port")
    done
    echo "${ports[@]}" | tr ' ' '&'
}

# Function to discover TiDB instances
discover_tidb() {
    local procs=$(ps -ef | grep 'tidb-server' | grep -v grep)
    if [ -z "$procs" ]; then
        echo "{}"
        exit 0
    fi

    while IFS= read -r proc; do
        local listener_pid=$(echo "$proc" | awk '{print $2}')
        listener_ports=$(get_listener_ports $listener_pid)
        if [ -z "$listener_ports" ]; then
            echo "{}"
            exit 0
        fi
        local exe=$(readlink -f /proc/$listener_pid/exe)
        local install_path=$( dirname $exe | sed 's/\/bin$//')
        local config_file="$(ps -p $listener_pid -o args= | grep -oP '(?<=--config=)[^\s]+')"
        local log_file=$(ps -p $listener_pid -o args= | grep -oP '(?<=--log-file=)[^\s]+')
        local version=$(get_tidb_version $install_path)
        local tidb_home=$(dirname $(dirname $exe))

        max_connections=""

        if [ -n "$config_file" ]; then
            eval $(get_config_content "$config_file")
            max_connections=${ret[max-server-connections]}
            max_connections="${max_connections//$'\r'/}"
        fi
        #从tikv获取redo日志和datafile路径
        redo_log=""
        dm_datafile=""
        tikv_procs=$(ps -ef | grep 'tikv-server' | grep -v grep| head -n 1)
        if [ -n "$tikv_procs" ]; then
              tikv_pid=$(echo "$tikv_procs" | awk '{print $2}')
              tikv_config_file="$(ps -p $tikv_pid -o args= | grep -oP '(?<=--config=)[^\s]+')"
              if [ -n "$tikv_config_file" ]; then
                  eval $(get_config_content "$tikv_config_file")
                  redo_log=$(echo "${ret[wal-dir]}" | sed 's/[\r"'\'']//g')
                  dm_datafile=$(echo "${ret[data-dir]}" | sed 's/[\r"'\'']//g')
              fi
        fi

        #判断是否集群
        dm_mode="single"
        pd_procs=$(ps -ef | grep 'pd-server' | grep -v grep)
        if [ -n "$pd_procs" ]; then
          pd_ctl_path=$install_path/bin/pd-ctl
          if [ -n "$pd_ctl_path" ]; then
              cluster_json=$($pd_ctl_path cluster)
              if echo "$cluster_json" | grep -q '"members"'; then
                  dm_mode="cluster"
              fi
          fi
        fi

        bk_host_innerip="{{bk_host_innerip}}"
        bk_inst_name="${bk_host_innerip}-tidb-${listener_ports}"

        tidb_info=$(printf '{"inst_name":"%s","dm_db_name":"tidb","ip_addr":"%s","port":"%s","version":"%s","dm_install_path":"%s","dm_conf_path":"%s","dm_log_file":"%s","dm_home_bash":"%s","dm_db_max_sessions":"%s","dm_redo_log":"%s","dm_datafile":"%s","dm_mode":"%s"}' \
            "$bk_inst_name" \
            "$bk_host_innerip" \
            "$listener_ports" \
            "$version" \
            "$install_path" \
            "$config_file" \
            "$log_file" \
            "$tidb_home" \
            "$max_connections" \
            "$redo_log" \
            "$dm_datafile" \
            "$dm_mode"
            )
        echo "$tidb_info"

    done <<< "$procs"
}

# Main script execution
discover_tidb

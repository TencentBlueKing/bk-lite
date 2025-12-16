#!/bin/bash

# Function to run command
run_cmd() {
    cmd=$1
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

# Function to get Redis processes
_procs() {
    local redis_dict=()
    local pids=$(ps -e -o pid,comm | grep redis-server | awk '{print $1}')
    for pid in $pids; do
        local cmdline=$(ps -p $pid -o args=)
        local exe=$(readlink -f /proc/$pid/exe)
        local install_path=$(dirname $exe | sed 's/\bin$//')
        local redis_cli=$(ps -p $pid -o comm= | sed 's/redis-server$/redis-cli/')

        # 修改正则表达式以匹配 IP 和端口
        # local ipport=$(echo $cmdline | grep -oP '([0-9]+.[0-9]+.[0-9]+.[0-9]+|*):[0-9]+')
        #local ipport=$(echo "$cmdline" | grep -oP '(?:[0-9]{1,3}.){3}[0-9]{1,3}(?::[0-9]+)?')
        local ipport=$(echo $cmdline | grep -oP '([\d.]+|\*):\d+')

        if [ -n "$ipport" ]; then
            local redis_ip=$(echo $ipport | cut -d: -f1)
            local redis_port=$(echo $ipport | cut -d: -f2)
            if [ "$redis_ip" = "*" ]; then
                redis_ip="0.0.0.0"
            fi
            redis_dict+=("$pid:$redis_ip:$redis_port:$redis_cli:$install_path")
        fi
    done
    echo "${redis_dict[@]}"
}

# Function to discover Redis
discover_redis() {
    local procs=($(_procs))
    if [ ${#procs[@]} -eq 0 ]; then
        echo "{}"
        exit 0
    fi

    # 获取主机内网 IP 地址
    bk_host_innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址

    # 用于记录已处理的端口，实现去重
    declare -A processed_ports

    for proc in "${procs[@]}"; do
        local pid=$(echo $proc | cut -d: -f1)
        local ip=$(echo $proc | cut -d: -f2)
        local port=$(echo $proc | cut -d: -f3)
        local redis_cli=$(echo $proc | cut -d: -f4)
        local install_path=$(echo $proc | cut -d: -f5)

        # 根据端口去重，如果该端口已处理过则跳过
        if [[ -n "${processed_ports[$port]}" ]]; then
            continue
        fi
        processed_ports[$port]=1

        # 替换为绝对路径
        install_path=$(readlink -f "$install_path")

        local version=$(run_cmd "$redis_cli --version" | awk '{print $2}')

        local max_clients=$(run_cmd "$redis_cli config get maxclients" | grep -A1 "maxclients" | tail -n1)

        local max_memory=$(run_cmd "$redis_cli config get maxmemory" | grep -A1 "maxmemory" | tail -n1)

        local role=$(run_cmd "$redis_cli info replication" | grep "role:" | awk -F: '{print $2}' | tr -d '\r')

        inst_name="${bk_host_innerip}-redis-${port}"

        # 修复 JSON 格式化问题，确保变量值正确插入
        redis_info=$(printf '{"inst_name":"%s","bk_obj_id":"redis","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","max_conn":"%s","max_mem":"%s","database_role":"%s"}' \
            "$inst_name" \
            "$bk_host_innerip" \
            "$port" \
            "$version" \
            "$install_path" \
            "$max_clients" \
            "$max_memory" \
            "$role"
        )

        echo "$redis_info"
    done
}

# Main script execution
discover_redis
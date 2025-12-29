#!/usr/bin/env bash

# Function to run command
run_cmd() {
    cmd="$1"
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

# Function to get Redis processes
_procs() {
    local redis_dict
    redis_dict=()
    local pids
    pids=$(ps -e -o pid,comm 2>/dev/null | grep redis-server | awk '{print $1}')
    
    for pid in $pids; do
        local cmdline
        cmdline=$(ps -p "$pid" -o args= 2>/dev/null)
        
        # 使用 awk 或 sed 替代 grep -oP (更兼容)
        local ipport
        ipport=$(echo "$cmdline" | sed -n 's/.*\([0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}\.[0-9]\{1,3\}:[0-9]\{1,5\}\).*/\1/p')
        
        # 如果没找到 IP:PORT 格式，尝试匹配 *:PORT 格式
        if [ -z "$ipport" ]; then
            ipport=$(echo "$cmdline" | sed -n 's/.*\(\*:[0-9]\{1,5\}\).*/\1/p')
        fi
        
        if [ -n "$ipport" ]; then
            local redis_ip redis_port redis_cli install_path exe
            redis_ip=$(echo "$ipport" | cut -d: -f1)
            redis_port=$(echo "$ipport" | cut -d: -f2)
            
            if [ "$redis_ip" = "*" ]; then
                redis_ip="0.0.0.0"
            fi
            
            # 获取 redis-cli 路径
            if [ -f "/proc/$pid/exe" ]; then
                exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
                install_path=$(dirname "$exe" 2>/dev/null | sed 's|/bin$||')
                redis_cli="${install_path}/bin/redis-cli"
            else
                # macOS 或其他不支持 /proc 的系统
                redis_cli="redis-cli"
                install_path=""
            fi
            
            redis_dict+=("$pid:$redis_ip:$redis_port:$redis_cli:$install_path")
        fi
    done
    echo "${redis_dict[@]}"
}

# Function to discover Redis
discover_redis() {
    local procs_output
    procs_output=$(_procs)
    
    # 转换为数组
    local procs
    read -r -a procs <<< "$procs_output"
    
    if [ ${#procs[@]} -eq 0 ]; then
        echo "{}"
        exit 0
    fi

    # 获取主机内网 IP 地址
    local bk_host_innerip
    if command -v hostname >/dev/null 2>&1; then
        bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    
    # 如果 hostname -I 不可用（如 macOS），尝试其他方法
    if [ -z "$bk_host_innerip" ]; then
        bk_host_innerip=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n1)
    fi
    
    # 默认值
    bk_host_innerip=${bk_host_innerip:-"127.0.0.1"}

    # 用于记录已处理的端口，实现去重（使用字符串模拟关联数组）
    local processed_ports=""

    for proc in "${procs[@]}"; do
        local pid ip port redis_cli install_path version max_clients max_memory role inst_name redis_info
        
        pid=$(echo "$proc" | cut -d: -f1)
        ip=$(echo "$proc" | cut -d: -f2)
        port=$(echo "$proc" | cut -d: -f3)
        redis_cli=$(echo "$proc" | cut -d: -f4)
        install_path=$(echo "$proc" | cut -d: -f5)

        # 根据端口去重，如果该端口已处理过则跳过
        if echo "$processed_ports" | grep -q "|$port|"; then
            continue
        fi
        processed_ports="$processed_ports|$port|"

        # 替换为绝对路径
        if [ -n "$install_path" ] && [ -d "$install_path" ]; then
            install_path=$(cd "$install_path" 2>/dev/null && pwd)
        fi

        # 获取 Redis 信息（添加端口参数）
        if [ -x "$redis_cli" ]; then
            version=$(run_cmd "$redis_cli -p $port --version" 2>/dev/null | awk '{print $2}')
            max_clients=$(run_cmd "$redis_cli -p $port config get maxclients" 2>/dev/null | grep -A1 "maxclients" | tail -n1)
            max_memory=$(run_cmd "$redis_cli -p $port config get maxmemory" 2>/dev/null | grep -A1 "maxmemory" | tail -n1)
            role=$(run_cmd "$redis_cli -p $port info replication" 2>/dev/null | grep "role:" | awk -F: '{print $2}' | tr -d '\r')
        else
            version=""
            max_clients=""
            max_memory=""
            role=""
        fi

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
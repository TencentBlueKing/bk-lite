#!/bin/bash

# 获取 PostgreSQL 信息（兼容 Ubuntu 和 CentOS）
host_innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址
# 1. 检测 PostgreSQL 主进程
find_postgres_pid() {
    # 尝试多种方式查找 postmaster 进程
    local pg_pid=$(ps aux | grep '[p]ostgres: checkpointer' | awk '{print $2}' | head -1)
    
    if [ -z "$pg_pid" ]; then
        pg_pid=$(ps aux | grep '[p]ostgres: background writer' | awk '{print $2}' | head -1)
    fi
    
    if [ -z "$pg_pid" ]; then
        pg_pid=$(ps aux | grep '[p]ostgres .* -D' | awk '{print $2}' | head -1)
    fi
    
    if [ -z "$pg_pid" ]; then
        echo "{}" >&2
        return 1
    fi
    
    echo "$pg_pid"
    return 0
}

# 2. 获取 PostgreSQL 版本
get_pg_version() {
    # 尝试多种方式获取版本
    if command -v postgres &> /dev/null; then
        postgres --version | awk '{print $3}'
    elif command -v pg_config &> /dev/null; then
        pg_config --version | awk '{print $2}'
    elif [ -d "/usr/lib/postgresql" ]; then
        ls /usr/lib/postgresql | sort -V | tail -1
    elif [ -d "/usr/pgsql" ]; then
        ls /usr/pgsql | sort -V | tail -1
    else
        echo "unknown版本"
    fi
}

# 3. 查找配置文件
find_config_file() {
    local pg_pid="$1"
    
    # 尝试从进程参数获取
    local config_file=$(ps -p $pg_pid -o args --no-headers | tr ' ' '\n' | \
                       grep -E 'config_file|--config-file' | cut -d= -f2 | head -1)
    
    # 如果未找到，尝试常见位置
    if [ -z "$config_file" ] || [ ! -f "$config_file" ]; then
        # 获取数据目录
        local data_dir=$(find_data_directory "$pg_pid")
        
        # Ubuntu/Debian 常见位置
        if [ -z "$config_file" ] && [ -d "/etc/postgresql" ]; then
            local pg_version=$(get_pg_version)
            local possible_paths=(
                "/etc/postgresql/$pg_version/main/postgresql.conf"
                "/etc/postgresql/$pg_version/postgresql.conf"
            )
            
            for path in "${possible_paths[@]}"; do
                if [ -f "$path" ]; then
                    config_file="$path"
                    break
                fi
            done
        fi
        
        # CentOS/RHEL 常见位置
        if [ -z "$config_file" ] && [ -d "/var/lib/pgsql" ]; then
            local pg_version=$(get_pg_version)
            local possible_paths=(
                "/var/lib/pgsql/$pg_version/data/postgresql.conf"
                "/var/lib/pgsql/data/postgresql.conf"
            )
            
            for path in "${possible_paths[@]}"; do
                if [ -f "$path" ]; then
                    config_file="$path"
                    break
                fi
            done
        fi
        
        # 通用位置
        if [ -z "$config_file" ] && [ -n "$data_dir" ]; then
            local possible_paths=(
                "$data_dir/postgresql.conf"
                "$data_dir/../postgresql.conf"
            )
            
            for path in "${possible_paths[@]}"; do
                if [ -f "$path" ]; then
                    config_file="$path"
                    break
                fi
            done
        fi
    fi
    
    echo "$config_file"
}

# 4. 查找数据目录
find_data_directory() {
    local pg_pid="$1"
    
    # 尝试从进程参数获取
    local data_dir=$(ps -p $pg_pid -o args --no-headers | tr ' ' '\n' | \
                    grep -E 'data_directory|--pgdata' | cut -d= -f2 | head -1)
    
    # 如果未找到，尝试常见位置
    if [ -z "$data_dir" ] || [ ! -d "$data_dir" ]; then
        # Ubuntu/Debian 常见位置
        if [ -d "/var/lib/postgresql" ]; then
            local pg_version=$(get_pg_version)
            local possible_paths=(
                "/var/lib/postgresql/$pg_version/main"
                "/var/lib/postgresql/$pg_version"
            )
            
            for path in "${possible_paths[@]}"; do
                if [ -d "$path" ]; then
                    data_dir="$path"
                    break
                fi
            done
        fi
        
        # CentOS/RHEL 常见位置
        if [ -z "$data_dir" ] && [ -d "/var/lib/pgsql" ]; then
            local pg_version=$(get_pg_version)
            local possible_paths=(
                "/var/lib/pgsql/$pg_version/data"
                "/var/lib/pgsql/data"
            )
            
            for path in "${possible_paths[@]}"; do
                if [ -d "$path" ]; then
                    data_dir="$path"
                    break
                fi
            done
        fi
    fi
    
    echo "$data_dir"
}

# 5. 解析配置文件参数
function parse_config_param() {
    local config_file="$1"
    local param_name="$2"
    
    if [ ! -f "$config_file" ]; then
        echo "unknown"
        return
    fi
    
    # 修复sed命令顺序：先移除注释再清理空格，最后处理引号
    local value=$(grep -E "^${param_name}\s*=" "$config_file" | \
                 tail -1 | awk -F= '{print $2}' | \
                 sed -e 's/#.*$//' -e 's/^\s*//' -e 's/\s*$//' -e "s/'//g" -e 's/"//g')
    
    # 如果未找到，尝试查找包含参数的文件
    if [ -z "$value" ]; then
        local include_dir=$(dirname "$config_file")
        local includes=$(grep -E '^\s*include\s*=' "$config_file" | \
                       awk -F= '{print $2}' | sed -e 's/#.*$//' -e "s/'//g" -e 's/"//g')
        
        for include in $includes; do
            if [[ "$include" != /* ]]; then
                include="${include_dir}/${include}"
            fi
            
            if [ -f "$include" ]; then
                # 同步修改包含文件的解析逻辑
                value=$(grep -E "^${param_name}\s*=" "$include" | \
                       tail -1 | awk -F= '{print $2}' | \
                       sed -e 's/#.*$//' -e 's/^\s*//' -e 's/\s*$//' -e "s/'//g" -e 's/"//g')
                if [ -n "$value" ]; then
                    break
                fi
            fi
        done
    fi
    
    echo "${value:-unknown}"
}

# 6. 转换共享缓存大小为 MB
convert_to_mb() {
    local value="$1"
    
    if [[ "$value" == *GB ]]; then
        local num=$(echo "$value" | sed 's/GB//')
        echo "$num * 1024" | bc
    elif [[ "$value" == *MB ]]; then
        echo "$value" | sed 's/MB//'
    elif [[ "$value" == *kB ]]; then
        local num=$(echo "$value" | sed 's/kB//')
        echo "scale=2; $num / 1024" | bc
    elif [[ "$value" == *B ]]; then
        local num=$(echo "$value" | sed 's/B//')
        echo "scale=2; $num / (1024*1024)" | bc
    else
        echo "$value"
    fi
}

# 7. 获取日志目录
get_log_directory() {
    local config_file="$1"
    local data_dir="$2"
    
    # 获取配置的日志目录
    local log_dir=$(parse_config_param "$config_file" "log_directory")
    
    # 处理相对路径
    if [[ "$log_dir" != /* ]] && [[ "$log_dir" != "unknown" ]]; then
        log_dir="${data_dir}/${log_dir}"
    fi
    
    # 如果未配置，尝试常见位置
    if [ -z "$log_dir" ] || [ "$log_dir" = "unknown" ] || [ ! -d "$log_dir" ]; then
        # Ubuntu/Debian 常见位置
        if [ -d "/var/log/postgresql" ]; then
            log_dir="/var/log/postgresql"
        # CentOS/RHEL 常见位置
        elif [ -n "$data_dir" ]; then
            if [ -d "${data_dir}/pg_log" ]; then
                log_dir="${data_dir}/pg_log"
            elif [ -d "${data_dir}/log" ]; then
                log_dir="${data_dir}/log"
            fi
        fi
    fi
    
    echo "${log_dir:-unknown}"
}

# 主函数
main() {
    # 查找 PostgreSQL 进程
    local pg_pid=$(find_postgres_pid)
    [ -z "$pg_pid" ] && exit 1

    # 获取数据目录
    local data_dir=$(find_data_directory "$pg_pid")

    # 获取配置文件
    local config_file=$(find_config_file "$pg_pid")

    # 获取端口：优先从配置文件中读取
    local port=$(parse_config_param "$config_file" "port")

    # 若配置文件中未找到，则尝试通过 ss 命令获取
    if [ "$port" = "unknown" ] || [ -z "$port" ]; then
        port=$(ss -tulnp "$pg_pid" 2>/dev/null | grep 'tcp.*LISTEN' | awk '{print $5}' | cut -d: -f2 | head -1)
    fi

    port=${port:-5432}
    
    # 获取版本
    local version=$(get_pg_version)

    # 获取最大连接数
    local max_connections=$(parse_config_param "$config_file" "max_connections")

    # 获取共享缓存大小并转换为 MB
    local shared_buffers=$(parse_config_param "$config_file" "shared_buffers")
    local shared_buffers_mb="unknown"
    if [ "$shared_buffers" != "unknown" ]; then
        shared_buffers_mb=$(convert_to_mb "$shared_buffers")
    fi

    # 获取日志目录
    local log_dir=$(get_log_directory "$config_file" "$data_dir")

    # 输出 JSON
cat <<EOF
{
    "inst_name": "${host_innerip}-pg-$port",
    "ip_addr": "$host_innerip",
    "port": "$port",
    "obj_id": "postgresql",
    "version": "$version",
    "conf_path": "$config_file",
    "data_path": "$data_dir",
    "max_conn": "$max_connections",
    "cache_memory_mb": "$shared_buffers_mb",
    "log_path": "$log_dir"
}
EOF
}

# 执行主函数
main

#!/bin/bash

# 获取内网 IP
bk_host_innerip=$(hostname -I | awk '{print $1}')

# 获取进程监听端口 (支持多端口以 & 分隔)
Get_Port_Join_Str() {
    local pid=$1
    # 使用 ss 或 netstat 准确获取该 PID 监听的 TCP 端口
    port_str=$(netstat -ntlp | grep -w "$pid" | awk '{print $4}' | awk -F ':' '{print $NF}' | sort -u | tr '\n' '&' | sed 's/&$//')
}

# 获取 Nginx 进程 PID 列表
Get_Nginx_Pid(){
    nginx_pid=()
    # 仅匹配 master 进程，因为 master 进程持有配置和二进制信息
    local pids=$(ps -ef | grep "nginx: master process" | grep -v grep | awk '{print $2}')
    
    # 如果没找到 master，尝试找普通进程
    if [ -z "$pids" ]; then
        pids=$(ps -ef | grep nginx | grep -v grep | awk '{print $2}')
    fi

    for pid in $pids; do
        # 校验：必须有监听端口
        if ! netstat -ntlp | grep -qw "$pid"; then continue; fi
        # 校验：可执行文件必须包含 nginx
        local exe=$(readlink -f /proc/$pid/exe 2>/dev/null)
        if [[ "$exe" == *nginx* ]]; then
            nginx_pid+=("$pid")
        fi
    done
}

# 核心：精准获取配置文件路径
Get_Nginx_Conf_Path() {
    local pid=$1
    local exe=$2
    # 1. 从进程启动命令行参数 -c 获取
    local conf=$(cat /proc/$pid/cmdline | tr '\0' '\n' | grep -A1 "\-c" | grep -v "\-c" | head -n1)
    
    # 2. 如果没有 -c，从 nginx -V 编译参数中提取 --conf-path
    if [ -z "$conf" ]; then
        conf=$($exe -V 2>&1 | grep -oP '(?<=--conf-path=)\S+')
    fi
    
    # 3. 转化为绝对路径并校验
    if [[ "$conf" != /* ]]; then
        local base=$(dirname $(dirname "$exe"))
        conf=$(readlink -f "$base/$conf")
    fi
    echo "$conf"
}

# 安全提取配置字段的函数
Extract_Conf_Value() {
    local file=$1
    local key=$2
    if [ -f "$file" ]; then
        # 匹配 key 后的第一个参数，去掉末尾分号
        grep -iE "^\s*$key" "$file" | head -n 1 | awk '{print $2}' | sed 's/;$//' | sed 's/"//g'
    else
        echo "unknown"
    fi
}

Cover_Nginx(){
    Get_Nginx_Pid
    
    # 避免重复处理同一个端口实例
    declare -A processed_ports

    for pid in "${nginx_pid[@]}"; do
        Get_Port_Join_Str "$pid"
        exe_path=$(readlink -f /proc/"$pid"/exe)
        
        # 唯一标识判断
        local inst_key="${bk_host_innerip}-nginx-${port_str}"
        if [[ -n "${processed_ports[$inst_key]}" ]]; then continue; fi
        processed_ports[$inst_key]=1

        # 获取版本和配置路径
        local version=$($exe_path -v 2>&1 | grep -oP '(?<=nginx/)\S+')
        local conf_path=$(Get_Nginx_Conf_Path "$pid" "$exe_path")
        
        # 从配置文件中提取信息
        local log_path=$(Extract_Conf_Value "$conf_path" "error_log")
        local server_name=$(Extract_Conf_Value "$conf_path" "server_name")
        local include_path=$(Extract_Conf_Value "$conf_path" "include")
        local ssl_ver=$(openssl version | awk '{print $2}')

        # 兜底处理
        [ -z "$log_path" ] && log_path="unknown"
        [ -z "$server_name" ] && server_name="unknown"
        [ -z "$include_path" ] && include_path="unknown"

        # 输出 JSON
        printf '{"inst_name": "%s-nginx-%s", "bk_obj_id": "nginx", "ip_addr": "%s", "port": "%s", "bin_path": "%s", "version": "%s", "log_path": "%s", "conf_path": "%s", "server_name": "%s", "include": "%s", "ssl_version": "%s"}\n' \
            "$bk_host_innerip" "$port_str" "$bk_host_innerip" "$port_str" "$exe_path" "$version" "$log_path" "$conf_path" "$server_name" "$include_path" "$ssl_ver"
    done
}

Cover_Nginx
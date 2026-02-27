#!/bin/bash
bk_host_innerip=$(hostname -I | awk '{print $1}')

Get_Nginx_Ports_From_Conf() {
    local conf_file="$1"
    local install_path="$2"
    local ports=()

    # 检查配置文件是否存在
    if [ ! -f "$conf_file" ]; then
        echo ""
        return
    fi

    # 解析当前配置文件中的listen端口
    local listen_lines=$(grep -E '^\s*listen\s+' "$conf_file" | grep -v '#' | awk '{print $2}' | sed -e 's/;//g' -e 's/default_server//g' -e 's/ssl//g' -e 's/http2//g' -e 's/udp//g' -e 's/tcp//g')
    
    # 提取端口（处理 "80"、":80"、"*:80"、"0.0.0.0:80"、"127.0.0.1:80" 等格式）
    for line in $listen_lines; do
        local port=$(echo "$line" | awk -F ':' '{print $NF}' | grep -E '^[0-9]+$')
        if [ -n "$port" ]; then
            ports+=("$port")
        fi
    done

    # 处理include指令，递归解析子配置文件
    local include_paths=$(grep -E '^\s*include\s+' "$conf_file" | awk '{print $2}' | sed 's/;//g')
    for include in $include_paths; do
        # 处理相对路径
        if [[ "$include" != /* ]]; then
            include=$(dirname "$conf_file")/"$include"
        fi
        # 处理通配符（如 *.conf）
        if [[ "$include" == *"*"* ]]; then
            for sub_conf in $include; do
                if [ -f "$sub_conf" ]; then
                    # 递归调用，获取子配置文件的端口
                    local sub_ports=$(Get_Nginx_Ports_From_Conf "$sub_ports" "$install_path")
                    ports+=($sub_ports)
                fi
            done
        else
            if [ -f "$include" ]; then
                local sub_ports=$(Get_Nginx_Ports_From_Conf "$include" "$install_path")
                ports+=($sub_ports)
            fi
        fi
    done

    # 去重、排序并拼接成 & 分隔的字符串
    local port_str=$(printf "%s\n" "${ports[@]}" | sort -n | uniq | tr '\n' '&')
    port_str="${port_str%&}"  # 去掉最后一个 &
    echo "$port_str"
}
# Function to get process PID
Get_Nginx_Pid(){
    i=0
    nginx_pid=()
    pid_arr=$(ps -ef  | grep "nginx" | grep -v grep | grep 'master process' |awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
         # 过滤掉不是nginx的进程
        is_nginx=$(echo $(readlink /proc/$pid/exe) |grep -i nginx)
        if [ -z "$is_nginx" ];then
            continue
        fi
         # 筛选后的pid
        nginx_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}
# Function to get Nginx version
Get_Nginx_Version(){
    nginx_version=$("$1" -v 2>&1 | grep "nginx version" | awk -F'/' '{print $2}' | awk '{print $1}')
    echo "$nginx_version"
}

Cover_Nginx(){
    inst_name_array=()
    Get_Nginx_Pid
    for pid in "${nginx_pid[@]}"
    do
        exe_path=$(readlink /proc/"$pid"/exe)
        # if [[ "${inst_name_array[*]}" =~ $bk_host_innerip-nginx-$port_str ]]; then
        #     continue
        # fi
        
        # Get Nginx version
        nginx_version=$(Get_Nginx_Version "$exe_path")
        if [ -z "$nginx_version" ]; then
            continue
        fi
        # Get Nginx installation path
        install_path=$(dirname $(dirname "$exe_path"))
        # Get document root
        # Get command line arguments
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        
        # ==========================================
        # 核心修改：兼容解析 Nginx 配置文件路ps径
        # ==========================================
        # 1. 尝试从启动命令 -c 参数中获取配置文件路径
        nginx_conf=$(echo "$cmdline" | grep -oP '(?<=-c\s)\S+')

        # 2. 如果没有 -c 参数，则从 nginx -V 提取 --conf-path
        if [ -z "$nginx_conf" ]; then
            nginx_conf=$($exe_path -V 2>&1 | grep -oP '(?<=\--conf-path=).*?\s'| awk '{$1=$1};1')
        fi

        # 3. 兜底方案：如果前两步都失败，给定一个默认的相对路径
        if [ -z "$nginx_conf" ]; then
            nginx_conf="$install_path/conf/nginx.conf"
        fi
        
        port_str=$(Get_Nginx_Ports_From_Conf "$nginx_conf" "$install_path")
        # 兜底：如果配置文件解析不到端口，显示unknown
        if [ -z "$port_str" ]; then
            port_str="unknown"
        fi
        inst_name_array[${#inst_name_array[@]}]="$bk_host_innerip-nginx-$port_str"
        log_path=$(grep -i 'error_log' "$nginx_conf" | awk '{print $2}' | sed 's/;$//')
        # =============can extend key=================
        json_template='{ "bk_inst_name": "%s-nginx-%s", "bk_obj_id": "nginx", "ip_addr": "%s", "listen_port": "%s", "nginx_path": "%s", "version": "%s", "log_path": "%s", "config_path": "%s"}'
        json_string=$(printf "$json_template" "$bk_host_innerip" "$port_str" "$bk_host_innerip" "$port_str" "$exe_path" "$nginx_version" "$log_path" "$nginx_conf")
        echo "$json_string"
    done
}
Cover_Nginx

#!/bin/bash

host_innerip=$(hostname -I | awk '{print $1}')
Get_Soft_Pid(){
    i=0
    soft_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep $1 | awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
#        # 判断是不是java进程
#        is_java=$(readlink /proc/$pid/exe | grep java)
#        if [ -z "$is_java" ]; then
#            continue
#        fi
#        # 过滤掉蓝鲸sass 进程
#        userId=$(ps -ef | grep $1 | grep -w $pid | grep -v grep | awk '{print $1}')
#        if [[ "$userId" == "apps" ]]; then
#            continue
#        fi
        # 筛选后的pid
        soft_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Get_Common_Data(){
    path_mid=$(ps -eo user:20,pid,args | grep $1 | grep -w $2)
    user=$(echo $path_mid | awk '{print $1}')
    command_mid=$(echo $path_mid | awk '{print substr($0, index($0,$3))}')
    log_dir_path=$(echo $command_mid | grep -oPm1 "(?<=-Dzookeeper.log.dir=)[^ ]+")
    java_bin_path=$(echo $command_mid | awk '{print $1}')
    command_array=($command_mid)
    cfg_path=${command_array[-1]}
    cwd=$(readlink /proc/$pid/cwd)
    exe=$(readlink /proc/$pid/exe)
}

Get_Config_Context(){
    port=$(cat $1 | grep -oPm1 "(?<=clientPort=)[^ ]+")
}

GetZookeeperVersion(){
    local pid=$1
    local proc_cwd=$2
    version="unknown"
    install_path="unknown"

    # 1. 尝试从进程打开的文件句柄中精准定位 jar 包
    # 这样可以直接获取到实际运行中的 jar 包路径
    local jar_line=$(lsof -p $pid 2>/dev/null | grep -E 'zookeeper-[0-9].*\.jar$' | head -n 1)
    
    if [ -n "$jar_line" ]; then
        # 提取完整路径：从第9列到行尾（处理空格路径）
        local full_path=$(echo "$jar_line" | awk '{print substr($0, index($0,$9))}')
        install_path=$(dirname "$(dirname "$full_path")")
        # 提取版本号：匹配 zookeeper- 后面跟着的数字和点
        version=$(echo "$full_path" | grep -oP 'zookeeper-\K[0-9.]+(?=\.jar|-[0-9])')
    else
        # 2. Fallback: 如果没 lsof，尝试从 /proc/$pid/fd 查找
        local fd_path=$(ls -l /proc/$pid/fd 2>/dev/null | grep -E 'zookeeper-[0-9].*\.jar' | head -n 1 | awk '{print $NF}')
        if [ -n "$fd_path" ]; then
            install_path=$(dirname "$(dirname "$fd_path")")
            version=$(echo "$fd_path" | grep -oP 'zookeeper-\K[0-9.]+(?=\.jar)')
        fi
    fi

    # 3. 兜底方案：从 install_path 查找版本
    if [ "$version" == "unknown" ] && [ -d "$install_path" ]; then
        version=$(ls "$install_path/lib" 2>/dev/null | grep -oP 'zookeeper-\K[0-9.]+(?=\.jar)' | head -n 1)
    fi
}

# 新增函数：解析 Zookeeper 配置文件中的 tickTime、initLimit 和 syncLimit
Get_Zookeeper_Config(){
    local cfg_path=$1
    tick_time=$(grep -oPm1 "(?<=tickTime=)[^ ]+" $cfg_path)
    init_limit=$(grep -oPm1 "(?<=initLimit=)[^ ]+" $cfg_path)
    sync_limit=$(grep -oPm1 "(?<=syncLimit=)[^ ]+" $cfg_path)
    cluster_servers=$(grep -E "^server\.[0-9]+=" $cfg_path | cut -d'=' -f2 | tr '\n' ',' | sed 's/,$//')
}

# 新增函数：解析 Zookeeper 配置文件中的 dataDir
Get_Data_Path(){
    local cfg_path=$1
    data_path=$(grep -oPm1 "(?<=dataDir=)[^ ]+" $cfg_path)
}

Cover_Zookeeper(){
    condition='Dzookeeper'
    Get_Soft_Pid $condition
    if [ ${#soft_pid[@]} -eq 0 ]; then
        exit 1
    fi
    inst_name_array=()
    for pid in ${soft_pid[@]}
    do
        Get_Common_Data $condition $pid
        # Get Java version
        java_version=$("$java_bin_path" -version 2>&1 | awk -F '"' '/version/ {print $2}' | awk -F'_' '{print $1}')
        Get_Config_Context $cfg_path
        GetZookeeperVersion $pid $cwd
        Get_Zookeeper_Config $cfg_path
        Get_Data_Path $cfg_path

        if [[ -z $port ]]; then
            continue
        fi

        # 格式化实例名
        inst_name="${host_innerip}-zk-${port}"

        if [[ $inst_name_array =~ $inst_name ]]; then
            continue
        fi

        inst_name_array[${#inst_name_array[@]}]=$inst_name

        # 输出 JSON 格式数据
        printf '{ "inst_name": "%s", "obj_id": "zookeeper", "install_path": "%s", "port": "%s", "user": "%s", "log_path": "%s", "conf_path": "%s", "java_path": "%s", "ip_addr": "%s", "java_version": "%s", "version": "%s", "data_dir": "%s", "tick_time": "%s", "init_limit": "%s", "sync_limit": "%s", "server": "%s" }\n' \
        "$inst_name" "$install_path" "$port" "$user" "$log_dir_path" "$cfg_path" "$exe" "$host_innerip" "$java_version" "$version" "$data_path" "$tick_time" "$init_limit" "$sync_limit" "$cluster_servers"
    done
}

Cover_Zookeeper

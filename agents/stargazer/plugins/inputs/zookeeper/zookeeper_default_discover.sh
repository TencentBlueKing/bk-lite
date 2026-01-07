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
    # Check if lsof command exists
    if command -v lsof &> /dev/null; then
        # Use lsof to get version
        version=$(lsof -p $pid | grep 'lib/zookeeper-' | awk -F'-' '{print $NF}' | awk -F'.jar' '{print $1}' | head -n 1)
        install_path=$(lsof -p $pid | grep 'lib/zookeeper-' | awk '{print $9}' | awk -F'/lib' '{print $1}' | head -n 1)
    else
        # Fallback to default method
        if [[ "$2" == */ ]]; then
            lib_path="$2../lib"
        else
            lib_path="$2/../lib"
        fi
        version=$(ls $lib_path | grep zookeeper | grep "\.jar" | awk -F '-' '{print $NF}' | awk -F '.jar' '{print $1}' | head -n 1)
        install_path=$2
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
        echo "{}"
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
            echo "not found port"
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

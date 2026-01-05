#!/bin/bash
host_innerip=$(hostname -I | awk '{print $1}')

# 获取进程pid
Get_Pid(){
    name=$1
    pid_arr=$(ps -ef | grep $name | grep -v grep | awk '{print $2}')
    echo $pid_arr
}

# 获取JDK版本
Get_JDK_Version(){
    version=$($1 -version 2>&1 | grep 'version' | awk -F '"' '{print $2}')
    echo $version
}

# 读取配置文件
Read_Configfile(){
    configfile=$1
    grep -v '^#' $configfile | grep -v '^$' | xargs
}

# 获取配置项
Get_Config_Item(){
    config_data=$1
    item=$2
    echo $(echo $config_data | grep -oP "(?<=${item}=)[^ ]+")
}

# 获取端口号
Get_Port(){
    xml_content=$(cat $1)
    mquri=$(echo "$xml_content" | grep -oP '(?<=<transportConnector name="nio" uri=")[^"]+')
   if [ -z "$mquri" ]; then
        mquri=$(echo "$xml_content" | grep -oP '<transportConnector[^>]*uri="[^"]+"' | head -n 1 | sed -E 's/.*uri="([^"]+)".*/\1/')
    fi
    
    mqport=$(echo "$mquri" | grep -oP '(?<=:)\d+(?=\?)')
    if [ -z "$mqport" ]; then
        mqport=61616
    fi
    echo $mqport
    
}

# 获取JVM参数
Get_JVM_Param(){
    param_name=$1
    echo "$(echo "$cmdline" | grep -oP "(?<=-${param_name})[0-9]+[a-zA-Z]*")"
}

# 主函数
Collect_ActiveMQ_Info(){
    pids=$(Get_Pid 'Dactivemq')
    if [ -z "$pids" ]; then
        echo '{}'
        exit 1
    fi
    
    for pid in $pids; do
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        cwd=$(readlink /proc/$pid/cwd)
        
        exe=$(readlink /proc/$pid/exe)
        base_path=$(echo "$cmdline" | grep -oP '(?<=-Dactivemq\.home=)[^ ]+' || echo "$cwd")
        conf_path=$(echo $cmdline | grep -oP '(?<=-Dactivemq.conf=)[^ ]+' | sed 's#//*#/#g' | xargs -I {} readlink -f {} | head -n 1)
        if [ -z "$conf_path" ]; then
            conf_path=$base_path/conf
        fi
        
        port=$(Get_Port $conf_path/activemq.xml)
        inst_name="$host_innerip-activemq-$port"
        hostip=$(hostname -I | awk '{print $1}')
        java_version=$(Get_JDK_Version $exe)
        version=$($base_path/bin/activemq --version | grep -oP '(?<=ActiveMQ )[^ ]+')
        
        # 获取JVM参数
        xms=$(Get_JVM_Param "Xms")
        xmx=$(Get_JVM_Param "Xmx")
        
        json_template='{ "inst_name": "%s", "obj_id": "activemq", "install_path": "%s", "port": "%s", "user": "%s", "conf_path": "%s", "java_path": "%s", "ip_addr": "%s", "java_version": "%s", "version": "%s", "xms": "%s", "xmx": "%s"}'
        json_string=$(printf "$json_template" "$inst_name" "$cwd" "$port" "$(ps -o user= -p $pid)" "$conf_path" "$exe" "$host_innerip" "$java_version" "$version" "$xms" "$xmx")
        echo "$json_string"
    done
}

Collect_ActiveMQ_Info


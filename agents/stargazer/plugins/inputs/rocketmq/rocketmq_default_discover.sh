#!/bin/bash

Get_Pid(){
    pid_arr=$(pgrep -f $1)
    echo $pid_arr
}

Get_RocketMQ_Version(){
    mqadmin_path=$1
    broker_addr=$2
    port=$3
    version=$(echo $mqadmin_path | grep -oP 'rocketmq-(\d+\.\d+\.\d+)' | grep -oP '(\d+\.\d+\.\d+)')
    if [ -z "$version" ]; then
        version=$($mqadmin_path brokerStatus --brokerAddr $broker_addr:$port | grep ^brokerVersionDesc | awk -F':' '{print $2}' | xargs)
    fi
    echo $version
}

Read_Configfile(){
    configfile=$1
    grep -v '^\s*#' $configfile | grep -v '^\s*$' | xargs
}

Get_Config_Item(){
    config_data=$1
    item=$2
    echo $(echo $config_data | grep -oP "(?<=${item}\s=\s)[^ ]+")
}

Collect_RocketMQ_Info(){
    pids=$(Get_Pid 'org.apache.rocketmq.broker.BrokerStartup')
    if [ -z "$pids" ]; then
        echo '{}'
        exit 0
    fi
    for pid in $pids; do
        java_path=$(readlink /proc/$pid/exe)
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        classpath=$(echo $cmdline | grep -oP '(?<=-cp\s)\S+')
        install_path=$(echo $classpath | grep -oP '[^:]*(?=/conf|/lib)' | head -n 1 | xargs -I {} readlink -f {})
        [ -z "$install_path" ] && continue
        configfile=$(echo $cmdline | grep -oP '(?<=-c\s)\S+')
        [ -z "$configfile" ] && configfile=$install_path/conf/broker.conf
        mqadmin=$install_path/bin/mqadmin
        hostip=$(hostname -I | awk '{print $1}')
        config_data=$(Read_Configfile $configfile)
        port=$(Get_Config_Item "$config_data" "listenPort")
        [ -z "$port" ] && port=10911
        version=$(Get_RocketMQ_Version $mqadmin $hostip $port)
        broker_id=$(Get_Config_Item "$config_data" "brokerId")
        broker_name=$(Get_Config_Item "$config_data" "brokerName")
        cluster_name=$(Get_Config_Item "$config_data" "brokerClusterName")
        namesrv_addr=$(Get_Config_Item "$config_data" "namesrvAddr")
        bk_inst_name="{{bk_host_innerip}}-rocketmq-$port"
        printf '{"bk_inst_name":"%s","bk_obj_id":"rocketmq","ip_addr":"{{bk_host_innerip}}","port":"%s","version":"%s","install_path":"%s","configfile":"%s","broker_id":"%s","broker_name":"%s","cluster_name":"%s","namesrv_addr":"%s","java_path":"%s"}\n' \
            "$bk_inst_name" "$port" "$version" "$install_path" "$configfile" "$broker_id" "$broker_name" "$cluster_name" "$namesrv_addr" "$java_path"
    done
}

Collect_RocketMQ_Info

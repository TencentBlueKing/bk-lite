#!/bin/bash
host_innerip=$(hostname -I | awk '{print $1}')
# 获取进程端口号
Get_Port_Join_Str(){
    port_arr_str=$(netstat -ntlp | grep $1 |awk '{print $4}'|awk -F ':' '{print $NF}'|sed 's/ *$//g'|sed 's/^ *//g'|sort|uniq)
    if [ -z "$port_arr_str" ];then
        continue
    fi
    port_str=""
    for port in ${port_arr_str[@]}
    do
        if [ -n "$port_str" ];then
            port_str=${port_str},${port}
        else
            port_str=${port}
        fi
    done
}
# 获取进程pid
Get_Mongo_Pid(){
    i=0
    mongo_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep $1 |awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
     # 过滤掉端口不存在的进程
        port_str=$(netstat -ntlp | grep -w $pid)
        if [ -z "$port_str" ];then
            continue
        fi
        # 过滤掉蓝鲸sass进程
        userId=$(ps -ef | grep $1 | grep -w $pid | grep -v grep | awk '{print $1}')
        if [[ "$userId" == "apps" ]];then
            continue
        fi
         # 过滤掉不是apache的进程
        is_mongo=$($(readlink /proc/$pid/exe) -v 2>/dev/null|grep -i mongo)
        if [ -z "$is_mongo" ];then
        	continue
        fi
         # 筛选后的pid
        mongo_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Cover_Mongo(){
    conditions=(mongo)
    inst_name_array=()
    for condition in ${conditions[@]}
    do
        Get_Mongo_Pid $condition
        for pid in ${mongo_pid[@]}
        do
            Get_Port_Join_Str $pid
            exe_path=$(readlink /proc/$pid/exe)
            if [[ $inst_name_array =~ $host_innerip-apache-$port_str ]];then
                continue
            fi
            bin_path=$(dirname $exe_path)
            mongo_path="$bin_path/mongo"
            if [[ ! -f "$mongo_path" ]]; then
                mongo_path=""
            fi
            inst_name="$host_innerip-mongodb-$port_str"
            inst_name_array[${#array_name[@]}]=$inst_name
            version=$($exe_path --version | grep -i "db version" | awk '{print $3}' | sed 's/^v//')
            cmd_expr="cat /proc/$pid/cmdline"
            config=$($cmd_expr | tr '\0' ' ' | grep -oP '(?<=--config)[^-]+|(?<=-f)[^-]+'|awk '{print $1}')
            if [[ ! -f "$config" ]]; then
                config="/etc/mongod.conf"
            fi

            # 最大并发连接数采集
            max_incoming_conn=$(cat $config 2>/dev/null | grep -v '^#' | awk '/^maxIncomingConnections:/ {print $2}' | sed 's/[;]//g')
            if [ -z "$max_incoming_conn" ]; then
                max_incoming_conn="default:819"
            fi

            # 数据库角色采集
            database_role=$($mongo_path --port $port_str -eval "rs.status()" 2>/dev/null | grep -i 'role' | awk '{print $2}' | head -n1)
            if [ -z "$database_role" ]; then
                database_role="standalone"
            fi

            fork=$(cat $config 2>/dev/null | grep -v '^#'|awk '/fork:/ {print $2}')
            system_log=$(cat $config 2>/dev/null | grep -v '^#'| awk '/systemLog:/,/\}/' | awk '/path:/ {print $2}')
            db_path=$(cat $config 2>/dev/null | grep -v '^#'  | awk '/storage:/,/\}/' | awk '/dbPath:/ {print $2}')

            json_str=$(printf '{"inst_name":"%s","ip_addr":"%s","obj_id":"mongodb","bin_path":"%s","mongo_path":"%s","port":"%s","version":"%s","config":"%s","fork":"%s","system_log":"%s","db_path":"%s","max_incoming_conn":"%s","database_role":"%s"}' \
            "$inst_name" "$host_innerip" "$bin_path" "$mongo_path" "$port_str" "$version" "$config"  "$fork" "$system_log" "$db_path" "$max_incoming_conn" "$database_role")
            echo $json_str
        done
    done
}
Cover_Mongo

            
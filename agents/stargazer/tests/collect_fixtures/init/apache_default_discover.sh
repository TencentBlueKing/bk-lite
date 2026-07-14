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
Get_Apache_Pid(){
    i=0
    apache_pid=()
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
        is_apache=$($(readlink /proc/$pid/exe) -v 2>/dev/null|grep -i apache)
        if [ -z "$is_apache" ];then
        	continue
        fi
         # 筛选后的pid
        apache_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

# 获取Apache版本
Get_Apache_Version(){
    apache_version=$($1 -v | grep "Server version" | awk -F'/' '{print $2}' | awk '{print $1}')
    echo $apache_version
}

# 获取文档根路径
Get_DocumentRoot(){
    document_root=$(grep -i 'DocumentRoot' $1 | awk -F '\"' '{print $2}')
    echo $document_root
}

# 获取错误日志路径
Get_Error_Log(){
    error_log=$(grep -i 'ErrorLog' $1 | awk -F '\"' '{print $2}')
    echo $error_log
}

# 获取自定义日志路径
Get_Custom_Log(){
    custom_log=$(grep -i 'CustomLog' $1 | awk -F '\"' '{print $2}')
    echo $custom_log
}

# 获取配置文件路径
Get_Httpd_Conf_Path(){
    # 优先从进程参数获取
    conf_path=$(ps -ef | grep $1 | grep -o '\-f[[:space:]]\+[^\ ]*' | awk '{print $2}')
    if [ -z "$conf_path" ];then
        # 根据系统默认路径判断
        if [ -f "/etc/httpd/conf/httpd.conf" ];then
            conf_path="/etc/httpd/conf/httpd.conf"
        elif [ -f "/etc/apache2/apache2.conf" ];then
            conf_path="/etc/apache2/apache2.conf"
        fi
    fi
    echo $conf_path
}

# 获取包含文件
Get_Include_Files(){
    include_files=$(grep -i '^Include' $1 | awk '{$1=""; print substr($0,2)}' | tr '\n' ',' | sed 's/,$//' | sed 's/ *//g')
    echo $include_files
}

Cover_Apache(){
    conditions=(httpd apache2 apache)
    inst_name_array=()
    for condition in ${conditions[@]}
    do
        Get_Apache_Pid $condition
        for pid in ${apache_pid[@]}
        do
            Get_Port_Join_Str $pid
            exe_path=$(readlink /proc/$pid/exe)
            if [[ $inst_name_array =~ '$host_innerip-apache-$port_str' ]];then
                continue
            fi
            inst_name_array[${#array_name[@]}]='$host_innerip-apache-$port_str'
            
            # 获取Apache版本
            apache_version=$(Get_Apache_Version $exe_path)
            
            # 获取配置文件路径
            httpd_conf_path=$(Get_Httpd_Conf_Path $exe_path)
            
            # 获取文档根路径
            document_root=$(Get_DocumentRoot "$httpd_conf_path")
            
            # 获取错误日志路径
            error_log=$(Get_Error_Log "$httpd_conf_path")
            
            # 获取自定义日志路径
            custom_log=$(Get_Custom_Log "$httpd_conf_path")
            
            # 获取包含文件
            include_files=$(Get_Include_Files "$httpd_conf_path")
            
            # =============can extend key=================
            json_template='{ "inst_name": "%s-apache-%s", "obj_id": "apache", "ip_addr": "%s", "port": "%s", "httpd_path": "%s", "version": "%s", "doc_root": "%s", "httpd_conf_path": "%s", "error_log": "%s", "custom_log": "%s", "include": "%s"}'
            json_string=$(printf "$json_template" "$host_innerip" "$port_str" "$host_innerip" "$port_str" "$exe_path" "$apache_version" "$document_root" "$httpd_conf_path" "$error_log" "$custom_log" "$include_files")
            echo "$json_string"
        done
    done
}
Cover_Apache
#!/bin/bash
# Phase 4 patch(2026-07-08):修 bk_host_innerip 模板替换 bug(同 Phase 3 memcached/haproxy 模式)
# 上游写死 bk_host_innerip={{bk_host_innerip}},runner 不替换;改 hostname 实际获取
# 同步策略:与 plugins/inputs/weblogic/weblogic_default_discover.sh 保持同步

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"
ip_str=$(ifconfig | grep inet |grep -v 127.0.0.1|awk '{print $2}'|head -1)
innerip=${ip_str##*:}

get_listen_port_from_config_xml(){
    tmp_path=$1
    svr_name=$2
    xml_content=$(cat $tmp_path)
    admin_server_name=$(echo "$xml_content" | grep -oPm1 "(?<=<admin-server-name>)[^<]+")

    # 提取domain-version的值
    domain_version=$(echo "$xml_content" | grep -oPm1 "(?<=<domain-version>)[^<]+")

    # 提取对应server的listen-port的值
    server_block=$(echo "$xml_content" | awk -v RS="</server>" -v FS="<server>" '/<name>'$svr_name'<\/name>/ {print $0}')
    listen_port=$(echo "$server_block" | grep -oPm1 "(?<=<listen-port>)[^<]+")

    if [ -z "$listen_port" ];then
        listen_port='7001'
    fi

}

Get_Soft_Pid(){
    i=0
    soft_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep $1 | grep "Dweblogic.home"|awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
      # 过滤掉端口不存在的进程
        port_str=$(netstat -ntlp | grep -w $pid)
        if [ -z "$port_str" ];then
            continue
        fi
        # 判断是不是java进程
        is_java=$(readlink /proc/$pid/exe | grep java)
        if [ -z "$is_java" ];then
         continue
        fi
        # 过滤掉蓝鲸sass 进程
        userId=$(ps -ef | grep $1 | grep -w $pid | grep -v grep | awk '{print $1}')
        if [[ "$userId" == "apps" ]];then
            continue
        fi
        # 筛选后的pid
        soft_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Get_Path(){
    wlst_path_mid=$(ps -ef | grep $1 | grep -w $2)
    wlpath_mid=${wlst_path_mid#*-Dwls.home=}
    wlst_path=$(echo $wlpath_mid|cut -d' ' -f1)
    name=$(echo "$wlst_path_mid" |  awk -F'-Dweblogic.Name=' '{print $2}' | awk '{print $1}')
    Dweblogic_home_mid=${wlst_path_mid#*-Dweblogic.home=}
    Dweblogic_home_path=$(echo $Dweblogic_home_mid | cut -d' ' -f1)
    java_home_path=$(echo $wlst_path_mid | awk '{print $8}' | awk -F'/bin/java' '{print $1}')
    cwd='/proc/'$2'/cwd'
    domain_path=$(ls -l $cwd | awk '{print $NF}')
    config_path=$domain_path'/config/config.xml'
}

Cover_Weblogic(){
    condition='Dweblogic.Name='
    Get_Soft_Pid $condition
    inst_name_array=()
    # 未启动weblogic服务直接打印空{}
    if [ ${#soft_pid[@]} -eq 0 ]; then
        echo "{}"
        exit 0
    fi

    for pid in ${soft_pid[@]}
    do
        Get_Path $condition $pid
        get_listen_port_from_config_xml $config_path $name

        # Get Java version
        java_version=$("$java_home_path/bin/java" -version 2>&1 | awk -F '"' '/version/ {print $2}' | awk -F'_' '{print $1}')
        # Format into single line JSON
        bk_inst_name=$bk_host_innerip-weblogic-$listen_port
        if [[ $inst_name_array =~ $bk_inst_name ]];then
            continue
        fi
        inst_name_array[${#inst_name_array[@]}]=$bk_inst_name
        current_datetime=$(date +%Y-%m-%d\ %H:%M:%S)
        json_template='{"inst_name": "%s", "bk_obj_id":"weblogic", "ip_addr": "%s", "port": "%s", "wlst_path": "%s", "java_version": "%s", "domain_version": "%s", "admin_server_name": "%s", "name":"%s", "domain_path": "%s"}'
        json_string=$(printf "$json_template" "$bk_inst_name" "$bk_host_innerip" "$listen_port" "$wlst_path" "$java_version" "$domain_version" "$admin_server_name" "$name" "$domain_path")
        echo "$json_string"
    done
}
Cover_Weblogic
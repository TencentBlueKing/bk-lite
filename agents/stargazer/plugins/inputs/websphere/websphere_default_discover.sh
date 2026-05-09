#!/bin/bash
bk_host_innerip={{bk_host_innerip}}
export LANG=en_US.UTF-8

Get_Soft_Pid(){
    i=0
    soft_pid=()
    pid_arr=$(ps -ef | grep -v grep | grep $1 | awk '{print $2}')
    for pid in ${pid_arr[@]}; do
        port_str=$(netstat -ntlp | grep -w $pid)
        [ -z "$port_str" ] && continue
        is_java=$(readlink /proc/$pid/exe | grep java)
        [ -z "$is_java" ] && continue
        userId=$(ps -ef | grep $1 | grep -w $pid | grep -v grep | awk '{print $1}')
        [[ "$userId" == "apps" ]] && continue
        soft_pid[$i]=$pid
        i=$(expr $i + 1)
    done
}

Get_Home_Path(){
    command_mid=$(ps -ef | grep $1 | grep -w $2)
    ser_name=$(echo $command_mid | awk '{print $NF}')
    node_name=$(echo $command_mid | awk '{print $(NF-1)}')
    cell_name=$(echo $command_mid | awk '{print $(NF-2)}')
}

get_soap_port(){
    soap=$(grep -o 'SOAP_CONNECTOR_ADDRESS.*port="[0-9]*"' "$1" | grep -o 'port="[0-9]*"' | sed 's/port=//;s/"//g' | head -1)
}

get_console_port(){
    console=$(grep -o 'WC_adminhost_secure.*port="[0-9]*"' "$1" | grep -o 'port="[0-9]*"' | sed 's/port=//;s/"//g' | head -1)
}

get_was_version(){
    x=$(bash $1/bin/versionInfo.sh 2>/dev/null)
    ver=$(echo $x | awk -F "Installed Product" '{print $NF}'| awk -F "Version" '{print $2}' |awk '{print $1}')
}

Cover_was(){
    condition='com.ibm.ws.runtime.WsServer'
    Get_Soft_Pid $condition
    [ ${#soft_pid[@]} -eq 0 ] && echo "{}" && exit 0
    for pid in ${soft_pid[@]}; do
        cwd=$(readlink "/proc/$pid/cwd")
        exe=$(readlink "/proc/$pid/exe")
        java_version=$($exe -version 2>&1 |awk 'NR==1{gsub(/"/,"");print $3}')
        Get_Home_Path $condition $pid
        cfg_file="$cwd/config/cells/$cell_name/nodes/$node_name/serverindex.xml"
        grep -q "ADMIN_AGENT" $cfg_file && continue
        grep -q "NODE_AGENT" $cfg_file && continue
        get_soap_port $cfg_file
        get_console_port $cfg_file
        get_was_version $cwd
        printf '{"bk_inst_name":"%s-was-%s","bk_obj_id":"websphere","version":"%s","install_path":"%s","bin_path":"%s/bin","java_version":"%s","ip_addr":"%s","port":"%s","java_path":"%s","server_name":"%s","cell":"%s","node":"%s","port_list":"%s"}\n' \
            "$bk_host_innerip" "$console" "$ver" "$cwd" "$cwd" "$java_version" "$bk_host_innerip" "$console" "$exe" "$ser_name" "$cell_name" "$node_name" "$soap"
    done
}

Cover_was

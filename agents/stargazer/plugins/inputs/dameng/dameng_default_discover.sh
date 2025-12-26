#!/bin/bash
bk_host_innerip={{bk_host_innerip}}

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
Get_DmPid(){
    i=0
    dm_pid=()
    dm_user=()
    dm_version=()
    dm_bin_path=()
    pid_arr=$(ps -ef | grep -v grep | grep -i "$1" |awk '{print $2}')
    for pid in ${pid_arr[@]}
    do
        # 过滤掉端口不存在的进程
        port_str=$(netstat -ntlp | grep -w $pid)
        if [ -z "$port_str" ];then
            continue
        fi

        # 获取用户名
        user=$(ps -o user= -p $pid)

        # 过滤掉非达梦进程,并获取版本号
        exe_path=$(readlink /proc/$pid/exe)
        version_info=$(su - $user -c "$exe_path -V" 2>/dev/null)
        is_dm=$(echo "$version_info" | grep -i dmap)
        if [ -z "$is_dm" ];then
            continue
        fi
        version=$(echo "$version_info"  | grep -oE '^dmap V[0-9]+' | awk '{print $2}')

        # 过滤掉蓝鲸sass进程
        if [[ "$user" == "apps" ]];then
            continue
        fi

        # 保存进程信息
        dm_pid[$i]=$pid
        dm_user[$i]=$user
        dm_version[$i]=$version
        dm_bin_path[$i]=$(dirname $exe_path)
        i=$(expr $i + 1)
    done
}

Cover_DaMeng(){
    condition=dmap
    Get_DmPid $condition
    # 未启动DaMeng服务直接打印空{}
    if [ ${#dm_pid[@]} -eq 0 ]; then
        echo "{}"
        exit 0
    fi
    for ((i=0; i<${#dm_pid[@]}; i++))
    do
        pid=${dm_pid[$i]}
        user=${dm_user[$i]}
        version=${dm_version[$i]}
        bin_path=${dm_bin_path[$i]}
        Get_Port_Join_Str $pid
        bk_inst_name="$bk_host_innerip-DaMeng-$port_str"
        json_str=$(printf '{"inst_name":"%s","ip_addr":"%s","port":"%s","user":"%s","version":"%s","bin_path":"%s","dm_db_name":"dameng"}' "$bk_inst_name" "$bk_host_innerip" "$port_str" "$user" "$version" "$bin_path")
        echo $json_str
    done
}

Cover_DaMeng

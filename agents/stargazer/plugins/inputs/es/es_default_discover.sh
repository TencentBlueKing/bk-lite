#!/bin/bash
# Function to get Java version
get_jdk_version() {
    jpath=$1
    if [[ -d "$jpath" ]]; then
        jpath="$jpath/bin/java"
    fi
    version=$($jpath -version 2>&1 | grep 'version' | awk -F '"' '{print $2}')
    echo $version
}

# Function to make command to dict
make_command() {
    command=$1
    declare -A ret_dict
    for i in $command; do
        if [[ $i == *=* ]]; then
            key=$(echo $i | cut -d '=' -f 1)
            value=$(echo $i | cut -d '=' -f 2-)
            ret_dict[$key]=$value
        fi
    done
    echo $(declare -p ret_dict)
}

# Function to get config content
get_config_content() {
    installpath=$1
    cfg_dir="${installpath}/config"  # 只保留目录部分
    declare -A ret
    if [[ ! -d "$cfg_dir" ]]; then
        return
    fi
    
    while IFS= read -r line; do
        if [[ $line == \#* ]]; then
            continue
        fi
        if [[ -z $line ]]; then
            continue
        fi
        if [[ $line == *http.port* || $line == *port:* ]]; then
            ret[port]=$(echo $line | grep -oP '(?<=:)\s*\K[0-9]+' | xargs)
        fi
        if [[ $line == *cluster.name* ]]; then
            ret[cluster_name]=$(echo $line | cut -d ':' -f 2 | xargs)
        fi
        if [[ $line == *node.name* ]]; then
            ret[node_name]=$(echo $line | cut -d ':' -f 2 | xargs)
        fi
        if [[ $line == *node.master* ]]; then
            ret[ismaster]=$(echo $line | grep -oP '(?<=:)\s*\K(true|false)' | xargs)
        fi
        if [[ $line == *path.data* ]]; then
            ret[data_path]=$(echo $line | cut -d ':' -f 2 | xargs)
        elif [[ $line == *path.logs* ]]; then
            ret[log_path]=$(echo $line | cut -d ':' -f 2 | xargs)
        fi
    done < "$cfg_dir/elasticsearch.yml"
    
    echo $(declare -p ret)
    echo "CFG_PATH=$cfg_dir"  # 确保导出配置目录路径
}

# Function to get ElasticSearch version
get_es_version() {
    installpath=$1
    lib_path="${installpath}/lib"
    version=$(find $lib_path -name 'elasticsearch-*.jar' 2>/dev/null | head -1 | grep -oP 'elasticsearch-.*\K[0-9]+\.[0-9]+\.[0-9]+')
    echo $version
}

# Function to get PID list
common_get_pid() {
    filterlist=("$@")
    grep_str=$(printf "%s|" "${filterlist[@]}" | sed 's/|$//')
    pid_list=()
    while IFS= read -r line; do
        all_list=($line)
        user=${all_list[0]}
        pid=${all_list[1]}
        cwd=$(readlink -f /proc/$pid/cwd)
        if [[ -z $cwd ]]; then
            continue
        fi
        exe=$(readlink -f /proc/$pid/exe)
        command=$(ps -p $pid -o args=)
        pid_list+=("${all_list[0]} $pid $exe $cwd $command")
    done < <(ps -ef | grep -E "$grep_str" | grep -v grep)
    echo "${pid_list[@]}"
}

# Main script to get ElasticSearch information
pid_list=$(common_get_pid 'elasticsearch' 'Des.path')
if [[ -z $pid_list ]]; then
    echo 'Not found process'
    exit 1
fi

for pid_info in "${pid_list[@]}"; do
    IFS=' ' read -r user pid exe cwd command <<< "$pid_info"

    eval $(make_command "$command")

    # 优先使用命令行参数获取安装路径
    install_path=${ret_dict[-Des.path.home]:-$cwd}
    # 新增安装路径下的默认jdk路径
    default_jdk_path="$install_path/jdk/bin/java"
    
    # 判断默认jdk路径是否存在且可执行
    if [[ -x "$default_jdk_path" ]]; then
        jdk_path="$default_jdk_path"
    else
        # 原有逻辑保持不变
        java_home=${ret_dict[-Des.java.home]}
        if [[ -n "$java_home" ]]; then
            jdk_path="$java_home/bin/java"
        else
            jdk_path="$exe"
        fi
    fi

    output=$(get_config_content "$install_path")
    eval $(get_config_content "$install_path")
    cfg_path=$(echo "$output" | grep ^CFG_PATH= | cut -d= -f2-)

    port=${ret[port]:-9200}
    innerip=$(hostname -I | awk '{print $1}')
    ismaster=false
    if [[ "${ret[ismaster]}" == "true" ]]; then
        ismaster=true
    fi

    json_template='{"inst_name":"%s","obj_id":"%s","install_path":"%s","port":"%s","conf_path":"%s","java_path":"%s","ip_addr":"%s","java_version":"%s","version":"%s","cluster_name":"%s","node_name":"%s","is_master":"%s","data_path":"%s","log_path":"%s"}'
    json_string=$(printf "$json_template" "${innerip}-es-${port}" "elasticsearch" "$install_path" "$port" "$cfg_path" "$jdk_path" "$innerip" "$(get_jdk_version "$jdk_path")" "$(get_es_version "$install_path")" "${ret[cluster_name]}" "${ret[node_name]}" "$ismaster" "${ret[data_path]}" "${ret[log_path]}")
    echo $json_string
done
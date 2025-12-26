#!/bin/bash

# 获取Java版本
get_jdk_version() {
    jpath=$1  # 接收java_path(exe)作为参数
    [[ -x "$jpath" ]] || { echo "unknown"; return; }  # 检查java_path是否可执行
    version=$($jpath -version 2>&1 | grep 'version' | awk -F '\"' '{print $2}')  # 执行java -version命令解析版本号
    echo ${version:-"unknown"}  # 输出版本号或unknown
}

# 获取Kafka版本
get_kafka_version() {
    installpath=$1
    [[ -z "$installpath" || ! -d "$installpath" ]] && { echo "unknown"; return; }
    [[ "$installpath" != */ ]] && installpath="${installpath}/"
    lib_path="${installpath}libs"
    [[ -d "$lib_path" ]] || { echo "unknown"; return; }
    version=$(find "$lib_path" -name 'kafka_*.jar' 2>/dev/null | head -1 | grep -oE 'kafka_[^-]+-[^-]+' | sed 's/^kafka_//;s/[.]jar$//')
    echo ${version:-"unknown"}
}

# 解析配置文件
parse_config() {
    cfg_path=$(readlink -f "$1")
    declare -A config_dict
    [[ -f "$cfg_path" ]] || { declare -p config_dict; return; }

    while IFS= read -r line; do
        line_trimmed=$(echo "$line" | xargs)
        [[ -z "$line_trimmed" || "$line_trimmed" == \#* ]] && continue
        if [[ "$line_trimmed" == *=* ]]; then
            key=$(echo "$line_trimmed" | cut -d'=' -f1 | awk '{$1=$1;print}')
            value=$(echo "$line_trimmed" | cut -d'=' -f2- | awk '{$1=$1;print}')
            config_dict["$key"]="$value"
        fi
    done < "$cfg_path"
    declare -p config_dict
}

# 生成未知实例
generate_unknown_instance() {
    innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址
    inst_name="${innerip}-kafka-unknown"

    cat <<EOF
{
    "inst_name": "$inst_name",
    "obj_id": "kafka",
    "ip_addr": "$innerip",
    "port": "unknown",
    "version": "unknown",
    "bin_path": "unknown",
    "conf_path": "unknown",
    "log_path": "unknown",
    "java_path": "unknown",
    "java_version": "unknown",
    "xms": "unknown",
    "xmx": "unknown",
    "broker_id": "unknown",
    "io_threads": "unknown",
    "network_threads": "unknown",
    "socket_receive_buffer_bytes": "unknown",
    "socket_request_max_bytes": "unknown",
    "socket_send_buffer_bytes": "unknown"
}
EOF
}

# 主函数
main() {
    # 获取Kafka进程
    pid_list=$(ps -ef | grep kafka.Kafka | grep -v grep | awk '{print $2}')

    # 如果没有Kafka进程，生成未知实例
    [[ -z "$pid_list" ]] && generate_unknown_instance && exit 0

    for pid in $pid_list; do
        # 初始化所有变量
        port="9092"
        install_path="unknown"
        cfg_path="unknown"
        log_path="unknown"
        exe="unknown"
        xms="unknown"
        xmx="unknown"
        broker_id="unknown"
        io_threads="unknown"
        network_threads="unknown"
        socket_receive="unknown"
        socket_request="unknown"
        socket_send="unknown"
        bin_path="unknown"
        kafka_version="unknown"
        java_version="unknown"

        # 获取进程基本信息
        command=$(ps -p $pid -o args=)
        cwd=$(readlink -f /proc/$pid/cwd)
        user=$(ps -p $pid -o user=)
        exe="unknown"

        # 尝试从命令行参数中提取java路径
        exe_from_command=$(echo "$command" | grep -oP '/.*?/bin/java' | head -1)

        if [[ -n "$exe_from_command" && -x "$exe_from_command" ]]; then
            exe=$(readlink -f "$exe_from_command")
        elif [[ -r /proc/$pid/exe ]]; then
            exe=$(readlink -f /proc/$pid/exe)
        fi

        # 解析配置文件路径
        cfg_param=$(echo "$command" | awk '{
            for(i=1; i<=NF; i++) {
                if ($i == "kafka.Kafka") {
            print $(i+1);
            exit;
        }
            }
        }')

        # 处理配置文件路径
        if [[ -n "$cfg_param" ]]; then
            if [[ "$cfg_param" != /* ]]; then
                if [[ "$cwd" == "/" ]]; then
                    cfg_path="/${cfg_param}"
                else
                    cfg_path="${cwd}/${cfg_param}"
                fi
            else
                cfg_path="$cfg_param"
            fi
            cfg_path=$(readlink -f "$cfg_path")
        fi

        # 解析配置文件内容
        if [[ -f "$cfg_path" ]]; then
            eval $(parse_config "$cfg_path")
        fi

        # 获取端口
        if [[ -n "${config_dict[listeners]}" ]]; then
            IFS=',' read -ra listeners <<< "${config_dict[listeners]}"
            for listener in "${listeners[@]}"; do
                if [[ "$listener" =~ [:/] ]]; then
                    port=$(echo "$listener" | awk -F: '{print $NF}' | tr -d ']' | cut -d'-' -f1)
                    [[ -n "$port" ]] && break
                fi
            done
        fi
        [[ "$port" == "unknown" ]] && port="${config_dict[port]}"
        [[ "$port" == "unknown" ]] && port="${config_dict[listeners]}" | awk -F: '{print $NF}'

        # 获取安装路径
        classpath=$(echo "$command" | grep -oP -- '-cp\s+\K\S+')
        [[ -z "$classpath" ]] && classpath=$(echo "$command" | grep -oP -- '-classpath\s+\K\S+')

        if [[ -n "$classpath" ]]; then
            path=$(echo "$classpath" | awk -F: '{print $1}')
            install_path=$(dirname "$path" | sed 's/\/libs$//;s/\/bin$//')
            install_path=$(readlink -f "$install_path")
        fi

        # 获取日志路径
        log_path=$(echo "$command" | grep -oP -- '-Dkafka\.logs\.dir=\K\S+')
        [[ -n "$log_path" ]] && log_path=$(readlink -f "$log_path")
        [[ -z "$log_path" && -n "${config_dict[log.dirs]}" ]] &&
            log_path=$(echo "${config_dict[log.dirs]}" | cut -d, -f1)
            [[ -n "$log_path" ]] && log_path=$(readlink -f "$log_path")

        # 获取Java内存设置
        xms=$(echo "$command" | grep -oP -- '-Xms\K\S+')
        xmx=$(echo "$command" | grep -oP -- '-Xmx\K\S+')

        # 获取其他配置参数
        broker_id="${config_dict[broker.id]:-unknown}"
        io_threads="${config_dict[num.io.threads]:-unknown}"
        network_threads="${config_dict[num.network.threads]:-unknown}"
        socket_receive="${config_dict[socket.receive.buffer.bytes]:-unknown}"
        socket_request="${config_dict[socket.request.max.bytes]:-unknown}"
        socket_send="${config_dict[socket.send.buffer.bytes]:-unknown}"

        # 计算bin路径
        if [[ "$install_path" != "unknown" ]]; then
            bin_path="${install_path}/bin"
        fi

        # 获取版本信息
        kafka_version=$(get_kafka_version "$install_path")
        java_version=$(get_jdk_version "$exe")  # java_version通过调用get_jdk_version函数获取，传入exe路径

        # 生成实例名
        innerip=$(hostname -I | awk '{print $1}')  # 获取第一个内网 IP 地址
        inst_name="${innerip}-kafka-${port}"

        # 生成JSON输出
        cat <<EOF
{
    "inst_name": "$inst_name",
    "obj_id": "kafka",
    "ip_addr": "$innerip",
    "port": "$port",
    "version": "$kafka_version",
    "install_path": "$bin_path",
    "conf_path": "$cfg_path",
    "log_path": "$log_path",
    "java_path": "$exe",
    "java_version": "$java_version",
    "xms": "$xms",
    "xmx": "$xmx",
    "broker_id": "$broker_id",
    "io_threads": "$io_threads",
    "network_threads": "$network_threads",
    "socket_receive_buffer_bytes": "$socket_receive",
    "socket_request_max_bytes": "$socket_request",
    "socket_send_buffer_bytes": "$socket_send"
}
EOF
    done
}

main
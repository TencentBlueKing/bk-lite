#!/bin/bash

host_innerip=$(hostname -I | awk '{print $1}')
export PATH="/usr/lib/rabbitmq/bin:/usr/sbin:/usr/local/sbin:$PATH"
cookie_file="/var/lib/rabbitmq/.erlang.cookie"
conf_default="/etc/rabbitmq/rabbitmq.conf"

find_rabbitmqctl() {
    if command -v rabbitmqctl >/dev/null 2>&1; then
        command -v rabbitmqctl
        return
    fi
    for bin in \
        /usr/lib/rabbitmq/bin/rabbitmqctl \
        /usr/local/lib/rabbitmq/bin/rabbitmqctl \
        /usr/sbin/rabbitmqctl \
        /usr/local/sbin/rabbitmqctl \
        /opt/rabbitmq/sbin/rabbitmqctl \
        /opt/rabbitmq/bin/rabbitmqctl; do
        if [ -x "$bin" ]; then
            echo "$bin"
            return
        fi
    done
}

prepare_cookie_env() {
    # 让 rabbitmqctl 使用服务端 cookie
    if [ -f "$cookie_file" ]; then
        export HOME="/var/lib/rabbitmq"
        export RABBITMQ_COOKIE="$(cat "$cookie_file" 2>/dev/null)"
    fi
}

detect_nodename() {
    # 优先从配置文件读取 node.name
    if [ -f "$conf_default" ]; then
        local n
        n=$(grep -E '^[[:space:]]*node\.name' "$conf_default" 2>/dev/null | awk -F'=' '{print $2}' | tr -d '[:space:]')
        if [ -n "$n" ]; then
            echo "$n"
            return
        fi
    fi
    # 常见默认名 rabbit@hostname
    echo "rabbit@$(hostname -s)"
}

get_rabbitmq_status() {
    local ctl_bin
    ctl_bin=$(find_rabbitmqctl)
    if [ -z "$ctl_bin" ]; then
        return 1
    fi
    prepare_cookie_env
    local nodename
    nodename=$(detect_nodename)

    # 逐个尝试不同 nodename，避免 hostname 不匹配导致连接失败
    local try_nodes=("$nodename" "rabbit@$(hostname -f)" "rabbit@localhost" "rabbit")
    for n in "${try_nodes[@]}"; do
        if [ -z "$n" ]; then
            continue
        fi
        out=$("$ctl_bin" -n "$n" status 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$out" ]; then
            echo "$out"
            return 0
        fi
    done
    return 1
}

get_rabbitmq_version() {
    echo "$1" | tr '\n' ' ' | grep -Eo '{rabbit,"RabbitMQ","[^"]+' | head -1 | awk -F'"' '{print $4}'
}

get_erlang_version() {
    local val
    val=$(echo "$1" | awk -F'"' '/erlang_version/ {print $2; exit}')
    if [ -z "$val" ]; then
        val=$(echo "$1" | grep -Eo 'Erlang/OTP[[:space:]]+[0-9.]+' | head -1 | awk '{print $2}')
    fi
    if [ -z "$val" ]; then
        if command -v erl >/dev/null 2>&1; then
            val=$(erl -eval 'erlang:display(erlang:system_info(otp_release)), halt().' -noshell 2>/dev/null | tr -d '\r' | tail -1)
        fi
    fi
    echo "$val"
}

get_enabled_plugin_file() {
    local val
    val=$(echo "$1" | awk -F'"' '/enabled_plugins_file/ {print $2; exit}')
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk -F"'" '/enabled_plugins_file/ {print $2; exit}')
    fi
    if [ -z "$val" ] && [ -f "/etc/rabbitmq/enabled_plugins" ]; then
        val="/etc/rabbitmq/enabled_plugins"
    fi
    echo "$val"
}

get_node_name() {
    # 先取“Status of node xxx”行
    local val
    val=$(echo "$1" | awk '/^Status of node / {print $4; exit}')
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk -F"'" '/{node/ {print $2; exit}')
    fi
    if [ -z "$val" ]; then
        val=$(echo "$1" | grep -Eo 'rabbit@[A-Za-z0-9._-]+' | head -1)
    fi
    echo "$val"
}

extract_list_field() {
    local content="$1"
    local key="$2"
    echo "$content" | tr -d '\r' | grep -E "${key},\[[^]]*\]" | head -1 | awk -F'[' '{print $2}' | awk -F']' '{print $1}' | tr -d '"' | tr ',' '\n' | sed '/^$/d' | paste -sd, -
}

get_log_files() {
    local val
    val=$(extract_list_field "$1" "log_files")
    if [ -z "$val" ] && [ -d "/var/log/rabbitmq" ]; then
        val=$(ls /var/log/rabbitmq/rabbit*.log 2>/dev/null | paste -sd, -)
    fi
    echo "$val"
}

get_config_files() {
    extract_list_field "$1" "config_files"
}

get_main_port() {
    echo "$1" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{amqp,[0-9]+,[^}]*}' | head -1 | awk -F',' '{print $2}'
}

get_all_ports() {
    echo "$1" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{[a-zA-Z0-9_]+,[0-9]+,"[^"]*"}' | sed 's/[{}]//g' | awk -F',' '{print $2 "(" $1 ")"}' | paste -sd, -
}

discover_rabbitmq() {
    status_output=$(get_rabbitmq_status)
    if [ $? -ne 0 ]; then
        # 无法获取状态时，输出最小信息避免全空
        printf '{
    "inst_name": "%s",
    "obj_id":"rabbitmq",
    "port": "%s",
    "allport": "%s",
    "ip_addr": "%s",
    "node_name": "",
    "log_path": "",
    "conf_path": "%s",
    "version": "",
    "enabled_plugin_file": "",
    "erlang_version": ""
}' \
"$host_innerip-rabbitmq-unknown" "" "" "$host_innerip" "$conf_default"
        exit 0
    fi
    rabbitmq_version=$(get_rabbitmq_version "$status_output")
    erlang_version=$(get_erlang_version "$status_output")
    enabled_plugin_file=$(get_enabled_plugin_file "$status_output")
    node_name=$(get_node_name "$status_output")
    log_files=$(get_log_files "$status_output")
    config_files=$(get_config_files "$status_output")
    # config_config为空时,给个默认值"/etc/rabbitmq/rabbitmq.conf"
    if [ -z "$config_files" ]; then
        config_files="/etc/rabbitmq/rabbitmq.conf"
    fi
    main_port=$(get_main_port "$status_output")
    # 优先 AMQP 端口，取不到则从监听列表取首个端口
    if [ -z "$main_port" ]; then
        main_port=$(echo "$status_output" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{[a-zA-Z0-9_]+,[0-9]+,"[^"]*"}' | head -1 | sed 's/[{}]//g' | awk -F',' '{print $2}')
    fi
    if [ -z "$main_port" ]; then
        main_port="unknown"
    fi
    all_ports=$(get_all_ports "$status_output")
    
    inst_name="$host_innerip-rabbitmq-$main_port"
    printf '{
    "inst_name": "%s",
    "obj_id":"rabbitmq",
    "port": "%s",
    "allport": "%s",
    "ip_addr": "%s",
    "node_name": "%s",
    "log_path": "%s",
    "conf_path": "%s",
    "version": "%s",
    "enabled_plugin_file": "%s",
    "erlang_version": "%s"
}
' \
"$inst_name" "$main_port" "$all_ports" "$host_innerip" "$node_name" "$log_files" "$config_files" "$rabbitmq_version" "$enabled_plugin_file" "$erlang_version"
}

discover_rabbitmq


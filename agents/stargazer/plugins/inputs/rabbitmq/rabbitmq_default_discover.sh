#!/bin/bash

host_innerip=$(hostname -I | awk '{print $1}')
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
    if [ -f "$cookie_file" ]; then
        export HOME="/var/lib/rabbitmq"
        export RABBITMQ_COOKIE="$(cat "$cookie_file" 2>/dev/null)"
    fi
}

detect_nodename() {
    if [ -f "$conf_default" ]; then
        local n
        n=$(grep -E '^[[:space:]]*node\.name' "$conf_default" 2>/dev/null | awk -F'=' '{print $2}' | tr -d '[:space:]')
        if [ -n "$n" ]; then
            echo "$n"
            return
        fi
    fi
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
    out=$("$ctl_bin" status 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$out" ]; then
        echo "$out"
        return 0
    fi
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

# 提取进程 PID
get_pid() {
    local val
    val=$(echo "$1" | awk -F':' '/^OS PID/ {print $2; exit}' | tr -d ' \r')
    if [ -z "$val" ]; then
        val=$(echo "$1" | tr -d '\n\r' | grep -Eo '\{pid,[[:space:]]*[0-9]+\}' | grep -Eo '[0-9]+' | head -1)
    fi
    echo "$val"
}

# 从底层环境变量读取
get_env_from_proc() {
    local pid="$1"
    local key="$2"
    if [ -n "$pid" ] && [ -f "/proc/$pid/environ" ]; then
        cat "/proc/$pid/environ" 2>/dev/null | tr '\0' '\n' | grep -E "^${key}=" | awk -F'=' '{print $2}' | tr -d '\r'
    fi
}

get_rabbitmq_version() {
    local val
    val=$(echo "$1" | grep -Eo 'RabbitMQ version:[[:space:]]+[^[:space:]]+' | head -1 | awk '{print $NF}')
    if [ -z "$val" ]; then
        val=$(echo "$1" | tr '\n' ' ' | grep -Eo '{rabbit,"RabbitMQ","[^"]+' | head -1 | awk -F'"' '{print $4}')
    fi
    echo "$val"
}

get_erlang_version() {
    local val
    val=$(echo "$1" | grep -Eo 'Erlang/OTP:?[[:space:]]+[0-9.]+' | head -1 | awk -F'[ :]+' '{print $NF}')
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk -F'"' '/erlang_version/ {print $2; exit}')
    fi
    if [ -z "$val" ]; then
        val=$(echo "$1" | grep -Eo 'Erlang/OTP[[:space:]]+[0-9.]+' | head -1 | awk '{print $2}')
    fi
    if [ -z "$val" ]; then
        if command -v erl >/dev/null 2>&1; then
            val=$(erl -eval 'erlang:display(erlang:system_info(otp_release)), halt().' -noshell 2>/dev/null | tr -d '\r' | tail -1)
        fi
    fi
    echo "$val" | tr -d '"'
}

get_enabled_plugin_file() {
    local val
    val=$(echo "$1" | awk -F':' '/Enabled plugins? file/ {print $2; exit}' | tr -d ' \r')
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk -F'"' '/enabled_plugins_file/ {print $2; exit}')
    fi
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk -F"'" '/enabled_plugins_file/ {print $2; exit}')
    fi
    echo "$val"
}

get_node_name() {
    local val
    val=$(echo "$1" | awk -F':' '/^Node name/ {print $2; exit}' | tr -d ' \r')
    if [ -z "$val" ]; then
        val=$(echo "$1" | awk '/^Status of node / {print $4; exit}')
    fi
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
    echo "$content" | tr -d '\n\r' | grep -Eo "\{${key},[[:space:]]*\[[^]]*\]\}" | head -1 | \
        awk -F'[' '{print $2}' | awk -F']' '{print $1}' | tr -d '"' | tr ',' '\n' | \
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed '/^$/d' | paste -sd, -
}

extract_38_list() {
    local content="$1"
    local header=$(echo "$2" | tr 'A-Z' 'a-z')
    
    echo "$content" | tr -d '\r' | awk -v hdr="$header" '
        tolower($0) ~ hdr {flag=1; next}
        flag {
            if ($0 ~ /^[^ \t*]/ && $0 !~ /^$/) {
                flag=0;
                next;
            }
            if ($0 ~ /\*/) {
                sub(/^[^*]*\*/, "");
                sub(/^[^a-zA-Z0-9\/.-]+/, "");
                if ($0 != "") print $0;
            }
        }
    ' | paste -sd, -
}

get_log_files() {
    local val
    val=$(extract_38_list "$1" "log file")
    if [ -z "$val" ]; then
        val=$(extract_list_field "$1" "log_files")
    fi
    echo "$val"
}

get_config_files() {
    local val
    val=$(extract_38_list "$1" "config file")
    if [ -z "$val" ]; then
        val=$(extract_list_field "$1" "config_files")
    fi
    echo "$val"
}

get_main_port() {
    local val
    val=$(echo "$1" | grep -iE 'protocol:[[:space:]]*amqp( |$|,)' | grep -Eo 'port:[[:space:]]*[0-9]+' | head -1 | awk -F':' '{print $2}' | tr -d ' ')
    if [ -z "$val" ]; then
        val=$(echo "$1" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{amqp,[0-9]+,[^}]*}' | head -1 | awk -F',' '{print $2}')
    fi
    echo "$val"
}

get_all_ports() {
    local val
    val=$(echo "$1" | grep -i 'protocol:' | grep -i 'port:' | sed -n 's/.*port:[[:space:]]*\([0-9]*\).*protocol:[[:space:]]*\([^, \r]*\).*/\1(\2)/p' | paste -sd, -)
    if [ -z "$val" ]; then
        val=$(echo "$1" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{[a-zA-Z0-9_]+,[0-9]+,"[^"]*"}' | sed 's/[{}]//g' | awk -F',' '{print $2 "(" $1 ")"}' | paste -sd, -)
    fi
    echo "$val"
}

discover_rabbitmq() {
    status_output=$(get_rabbitmq_status)
    if [ $? -ne 0 ]; then
        exit 0
    fi
    
    rabbitmq_version=$(get_rabbitmq_version "$status_output")
    erlang_version=$(get_erlang_version "$status_output")
    node_name=$(get_node_name "$status_output")
    
    # 第一顺位：尝试从 status 输出中提取
    enabled_plugin_file=$(get_enabled_plugin_file "$status_output")
    log_files=$(get_log_files "$status_output")
    config_files=$(get_config_files "$status_output")
    
    pid=$(get_pid "$status_output")
    
    # 第二顺位：如果提取不到，去底层扒系统环境变量
    if [ -z "$config_files" ]; then
        env_conf=$(get_env_from_proc "$pid" "RABBITMQ_CONFIG_FILE")
        if [ -n "$env_conf" ]; then config_files="$env_conf"; fi
    fi
    if [ -z "$log_files" ]; then
        env_log_base=$(get_env_from_proc "$pid" "RABBITMQ_LOG_BASE")
        if [ -n "$env_log_base" ] && [ -n "$node_name" ]; then log_files="${env_log_base}/${node_name}.log"; fi
    fi
    if [ -z "$enabled_plugin_file" ]; then
        env_plugins=$(get_env_from_proc "$pid" "RABBITMQ_ENABLED_PLUGINS_FILE")
        if [ -n "$env_plugins" ]; then enabled_plugin_file="$env_plugins"; fi
    fi

    # 第三顺位：直接扒进程启动命令 (ps/cmdline)
    if [ -n "$pid" ] && [ -f "/proc/$pid/cmdline" ]; then
        # tr '\0' ' ' 是因为 cmdline 内部以 null 分隔参数
        cmdline=$(cat "/proc/$pid/cmdline" 2>/dev/null | tr '\0' ' ')
        
        if [ -z "$log_files" ]; then
            # 捕获类似 -rabbit error_logger {file,"/var/log/rabbitmq/rabbit@localhost.log"}
            log_files=$(echo "$cmdline" | grep -Eo '\-rabbit error_logger \{file,"[^"]+"\}' | head -1 | awk -F'"' '{print $2}')
        fi
        
        if [ -z "$enabled_plugin_file" ]; then
            # 捕获类似 -rabbit enabled_plugins_file "/etc/rabbitmq/enabled_plugins"
            enabled_plugin_file=$(echo "$cmdline" | grep -Eo '\-rabbit enabled_plugins_file "[^"]+"' | head -1 | awk -F'"' '{print $2}')
        fi
        
        if [ -z "$config_files" ]; then
            # 捕获类似 -config /path/to/rabbitmq (老版本 erlang 会默认补充 .config)
            conf_tmp=$(echo "$cmdline" | grep -Eo '\-config [^ ]+' | head -1 | awk '{print $2}' | tr -d '"')
            if [ -n "$conf_tmp" ]; then
                config_files="$conf_tmp"
            fi
        fi
    fi
    
    main_port=$(get_main_port "$status_output")
    if [ -z "$main_port" ]; then
        main_port=$(echo "$status_output" | grep -i 'port:' | head -1 | sed -n 's/.*port:[[:space:]]*\([0-9]*\).*/\1/p')
        if [ -z "$main_port" ]; then
            main_port=$(echo "$status_output" | tr -d ' ' | tr '\n' ' ' | grep -Eo '{[a-zA-Z0-9_]+,[0-9]+,"[^"]*"}' | head -1 | sed 's/[{}]//g' | awk -F',' '{print $2}')
        fi
    fi
    if [ -z "$main_port" ]; then main_port="unknown"; fi
    
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
}\n' \
"$inst_name" "$main_port" "$all_ports" "$host_innerip" "$node_name" "$log_files" "$config_files" "$rabbitmq_version" "$enabled_plugin_file" "$erlang_version"
}

discover_rabbitmq
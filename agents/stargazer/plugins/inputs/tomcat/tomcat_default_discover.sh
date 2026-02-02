#! /bin/bash

get_host_ip() {
    hostname -I | awk '{print $1}'
}

get_tomcat_home() {
    ps -ef | grep Bootstrap | grep -vE "grep|openjdk" | awk -F"Dcatalina.home=" '{print $2}' | awk '{print $1}'
}

get_tomcat_context() {
    local tomcat_server="${1}/conf/server.xml"
    cat "$tomcat_server" | sed 's/<!--/\n<!--\n/' | sed 's/-->/\n-->/' | sed '/<!--/,/-->/ d' | sed '/-->/ d' | sed '/^\s*$/d'
}

get_tomcat_port() {
    local context="$1"
    echo "$context" | tr '\r' ' ' | tr '\n' ' ' | grep -Eo '<Connector[^>]*>' | grep port | grep -vEi "Define|support|Server|apache|SSLEnabled|AJP" | grep -v "<!" | awk -F "port=" '{print $2}' | awk '{print $1}' | awk -F'"' '{print $2}' | uniq
}

get_jvm_options() {
    local pid=$(ps -ef | grep -v grep | grep Bootstrap | awk '{print $2}')
    if [ -z "$pid" ]; then
        echo ""
        return
    fi

    if [ -f "/proc/$pid/cmdline" ]; then
        tr '\0' ' ' < "/proc/$pid/cmdline"
    else
        ps -ef | grep -v grep | grep "$pid" | sed 's/^[^ ]* [^ ]* [^ ]* [^ ]* //'
    fi
}

get_tomcat_version() {
    local base="$1"
    local version=""

    if [ -x "$base/bin/version.sh" ]; then
        version=$("$base/bin/version.sh" 2>/dev/null | awk -F'/' '/Apache Tomcat/{print $2; exit}')
    fi

    if [ -z "$version" ] && [ -x "$base/bin/catalina.sh" ]; then
        version=$("$base/bin/catalina.sh" version 2>/dev/null | awk -F'/' '/Server number: Apache Tomcat/{print $2; exit}')
        version=$(echo "$version" | tr -d '[:space:]')
    fi

    if [ -z "$version" ] && command -v rpm >/dev/null 2>&1; then
        version=$(rpm -q --qf '%{VERSION}' tomcat 2>/dev/null | head -1)
    fi

    if [ -z "$version" ] && command -v dpkg-query >/dev/null 2>&1; then
        version=$(dpkg-query -W -f='${Version}' tomcat 2>/dev/null | head -1)
    fi

    echo "$version"
}

get_jdk_version() {
    unset JDK_JAVA_OPTIONS 2>/dev/null
    java -version 2>&1 | grep -Eo 'version "[^"]+' | head -1 | awk -F'"' '{print $2}'
}

get_init_heap() {
    local opts="$1"
    echo "$opts" | tr ' ' '\n' | awk '/^-Xms/ {sub("^-Xms","",$0); if($0!=""){print $0; exit}}'
}

get_max_heap() {
    local opts="$1"
    echo "$opts" | tr ' ' '\n' | awk '/^-Xmx/ {sub("^-Xmx","",$0); if($0!=""){print $0; exit}}'
}

get_max_non_heap() {
    local opts="$1"
    echo "$opts" | tr ' ' '\n' | awk '
        /^-XX:MaxMetaspaceSize=/ {sub("^-XX:MaxMetaspaceSize=","",$0); if($0!=""){print $0; exit}}
        /^-XX:MaxPermSize=/ {sub("^-XX:MaxPermSize=","",$0); if($0!=""){print $0; exit}}
    '
}

get_init_non_heap() {
    local opts="$1"
    echo "$opts" | tr ' ' '\n' | awk '
        /^-XX:MetaspaceSize=/ {sub("^-XX:MetaspaceSize=","",$0); if($0!=""){print $0; exit}}
        /^-XX:PermSize=/ {sub("^-XX:PermSize=","",$0); if($0!=""){print $0; exit}}
    '
}

get_log_path() {
    local base="$1"
    local default_log="${base}/logs/catalina.out"
    if [ -f "$default_log" ]; then
        echo "$default_log"
    else
        find "${base}/logs" -name "catalina.out" 2>/dev/null | head -1
    fi
}

get_config_java_opts() {
    local base="$1"
    local opts=()

    # 1) 官方安装 setenv.sh
    local setenv="${base}/bin/setenv.sh"
    if [ -f "$setenv" ]; then
        opts+=("$(grep -Eh '^(export )?(JAVA_OPTS|CATALINA_OPTS)=' "$setenv" 2>/dev/null | sed 's/^export //;s/^[^=]*=//;s/^\"//;s/\"$//;s/^'\''//;s/'\''$//' )")
    fi

    # 2) 包管理安装常见配置
    for cfg in /etc/sysconfig/tomcat /etc/sysconfig/tomcat* /etc/default/tomcat /etc/default/tomcat* /etc/tomcat/tomcat.conf /etc/tomcat*/tomcat.conf "$base/conf/tomcat.conf"; do
        [ -f "$cfg" ] || continue
        opts+=("$(grep -Eh '^(export )?(JAVA_OPTS|CATALINA_OPTS)=' "$cfg" 2>/dev/null | sed 's/^export //;s/^[^=]*=//;s/^\"//;s/\"$//;s/^'\''//;s/'\''$//' )")
    done

    # 去重、合并
    echo "${opts[@]}" | tr ' ' '\n' | sed '/^$/d' | sort -u | tr '\n' ' '
}

discover_tomcat() {
    local host_ip=$(get_host_ip)
    local tomcat_home=$(get_tomcat_home)

    for b in $tomcat_home; do
        local tomcat_context=$(get_tomcat_context "$b")
        local tomcat_port=$(get_tomcat_port "$tomcat_context")

        if [[ ! "$tomcat_port" =~ ^[0-9]+$ ]]; then
            continue
        fi

        local jvm_opts=$(get_jvm_options)
        local config_opts=$(get_config_java_opts "$b")
        if [ -n "$config_opts" ]; then
            jvm_opts="$jvm_opts $config_opts"
        fi
        

        local version=$(get_tomcat_version "$b")
        local java_version=$(get_jdk_version)
        local xms=$(get_init_heap "$jvm_opts")
        local xmx=$(get_max_heap "$jvm_opts")
        local max_perm_size=$(get_max_non_heap "$jvm_opts")
        local permsize=$(get_init_non_heap "$jvm_opts")
        local log_path=$(get_log_path "$b")

        cat <<EOF
{
    "inst_name": "${host_ip}-tomcat-${tomcat_port}",
    "obj_id": "tomcat",
    "ip_addr": "${host_ip}",
    "port": "${tomcat_port}",
    "catalina_path": "${b}/bin/catalina.sh",
    "version": "${version}",
    "xms": "${xms}",
    "xmx": "${xmx}",
    "max_perm_size": "${max_perm_size}",
    "permsize": "${permsize}",
    "log_path": "${log_path}",
    "java_version": "${java_version}"
}
EOF
    done
}

discover_tomcat


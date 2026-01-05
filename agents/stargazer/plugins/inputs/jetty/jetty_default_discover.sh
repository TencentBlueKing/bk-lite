#!/bin/bash
bk_host_innerip="{{bk_host_innerip}}"
get_jetty_port() {
    port_arr_str=$(netstat -ntlp | grep "$1" | awk '{print $4}' | awk -F ':' '{print $NF}' | sed 's/ *$//g' | sed 's/^ *//g' | sort | uniq | tr '\
    ' '&' )
    echo "${port_arr_str%&}"
}
get_jetty_version() {
    local jetty_home=$1
    local jetty_version=$(find "$jetty_home/lib" -name 'jetty-client-*.jar' | head -1 | grep -oP 'jetty-client-\K[^\s]+(?=\.jar)')
    echo $jetty_version
}
convert_to_dict() {
    local exports
    exports=$(grep -E 'export JAVA_HOME=' ~/.bashrc)
    if [ -n "$exports" ]; then
        eval "$exports"
    fi
    export PATH=${JAVA_HOME}/bin:$PATH
    local jetty_exe=$1
    declare -A cmd_dict
    while IFS= read -r line; do
        if [[ $line == *=* ]]; then
            line=$(echo $line | sed 's/ *= */=/g')
            key=$(echo $line  | cut -d '=' -f 1)
            value=$(echo $line | cut -d '=' -f 2-)
            cmd_dict[$key]=$value
        fi
    done < <("$jetty_exe" check)
    echo $(declare -p cmd_dict)
}
get_jdk_version() {
    jpath=$1
    version=$($jpath -version 2>&1 | grep 'version' | awk -F '"' '{print $2}')
    echo $version
}
get_jdk_vendor() {
    java_path=$1
    vendor=$($java_path -XshowSettings:properties -version 2>&1 | grep 'java.vendor = ' | awk -F '= ' '{print $2}')
    echo $vendor
}

get_max_threads() {
    local jetty_home=$1
    JETTY_THREADPOOL_FILE="$jetty_home/etc/jetty-threadpool.xml"

    # 检查文件是否存在
    if [ ! -f "$JETTY_THREADPOOL_FILE" ]; then
        echo ""
        return
    fi

    MAX_THREADS=$(grep 'maxThreads' $JETTY_THREADPOOL_FILE | sed -n 's/.*default="\([0-9]\+\)".*/\1/p')
    # 检查是否成功提取
    if [ -z "$MAX_THREADS" ]; then
        echo ""
    else
        echo "$MAX_THREADS"
    fi
}

discover_jetty() {
    local procs=$(ps -ef | grep jetty | grep -v grep | grep -v "$0" | grep -v systemctl)
    if [ -z "$procs" ]; then
        echo "{}"
        exit 0
    fi
    while IFS= read -r proc; do
        pid=$(echo $proc | awk '{print $2}')
        home=$(echo $proc | grep -oP '(?<=-Djetty.home=)[^\s]+')
        port_str=$(get_jetty_port $pid)
        bin_path=$home/bin
        webapps_dir=$home/webapps/
        jetty_sh_path="$home/bin/jetty.sh"
        jetty_version=$(get_jetty_version "$home")
        if [ -f "$jetty_sh_path" ]; then
            eval $(convert_to_dict "$jetty_sh_path")
        else
            echo "{}"
            exit 0
        fi

        max_threads=$(get_max_threads "$home")
        war_name=$(find $webapps_dir -maxdepth 1 -type f -name "*.war" -exec basename {} \; | paste -sd "," -)
        java_path="${cmd_dict[JAVA]}"
        jvm_para="${cmd_dict[JAVA_OPTIONS]}"
        jdk_vendor=$(get_jdk_vendor "$java_path")
        java_version=$(get_jdk_version "$java_path")
        jetty_conf="${cmd_dict[JETTY_CONF]}"
        json_template='{"inst_name": "%s-jetty-%s", "bk_obj_id":"jetty","ip_addr": "%s", "port": "%s", "jetty_home": "%s", "bin_path": "%s", "monitored_dir": "%s", "version": "%s", "java_path": "%s", "java_version": "%s", "conf_path": "%s", "java_vendor": "%s", "war_name": "%s", "jvm_para": "%s", "max_threads": "%s"}'
        json_string=$(printf "$json_template" "$bk_host_innerip" "$port_str" "$bk_host_innerip" "$port_str" "$home" "$bin_path" "$webapps_dir" "$jetty_version" "$java_path" "$java_version" "$jetty_conf" "$jdk_vendor" "$war_name" "$jvm_para" "$max_threads")
        echo $json_string
    done <<< "$procs"
}
discover_jetty
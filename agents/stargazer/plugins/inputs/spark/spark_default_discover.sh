#!/bin/bash

bk_host_innerip={{bk_host_innerip}}

run_cmd() {
    cmd=$1
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}

re_search() {
    pattern=$1
    string=$2
    result=$(echo "$string" | grep -oP "$pattern")
    echo "$result"
}

_procs() {
    ps -ef | grep 'org.apache.spark.deploy.master.Master' | grep -v grep
}

_spark_home() {
    cmdline=$1
    spark_home=$(echo "$cmdline" | grep -oP '(?<=-cp\s)(/.+)(?=/conf)')
    [ -z "$spark_home" ] && spark_home=$SPARK_HOME
    echo "$spark_home"
}

_spark_version() {
    sparkshell=$1
    [ ! -f "$sparkshell" ] && return
    versioninfo=$(run_cmd "$sparkshell --version")
    version=$(re_search '(?<=version\s)(\d+\.\d+\.\d+)' "$versioninfo")
    version=$(echo "$version" | awk 'NR==1{print $1}')
    echo "$version"
}

discover_spark_master() {
    procs=$(_procs)
    [ -z "$procs" ] && echo "{}" && exit 0
    while read -r proc; do
        install_path=$(_spark_home "$proc")
        spark_shell="$install_path/bin/spark-shell"
        version=$(_spark_version "$spark_shell")
        master_port=$(re_search '(?<=--port\s)(\d+)' "$proc")
        webui_port=$(re_search '(?<=--webui-port\s)(\d+)' "$proc")
        log_dir=$(re_search '(?<=-Dspark.log.dir=)\S+' "$proc")
        [ -z "$log_dir" ] && log_dir="$install_path/logs"
        java_path=$(echo "$proc" | awk '{print $8}')
        java_version=$($java_path -version 2>&1 | awk -F '"' '/version/ {print $2}')
        bk_inst_name="${bk_host_innerip}-spark-${master_port}"
        printf '{"bk_inst_name":"%s","bk_obj_id":"spark","ip_addr":"%s","port":"%s","install_path":"%s","version":"%s","webui_port":"%s","java_path":"%s","java_version":"%s","log_path":"%s"}\n' \
            "$bk_inst_name" "$bk_host_innerip" "$master_port" "$install_path" "$version" "$webui_port" "$java_path" "$java_version" "$log_dir"
    done <<< "$procs"
}

discover_spark_master

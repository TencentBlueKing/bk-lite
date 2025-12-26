#!/bin/bash
bk_host_innerip={{bk_host_innerip}}
# Run command and return the result
run_cmd() {
    cmd=$1
    result=$(eval "$cmd" 2>&1)
    echo "$result"
}
# Regular expression search
re_search() {
    pattern=$1
    string=$2
    echo "$string" | grep -oP "$pattern"
}
# Get JDK version
get_jdk_version() {
    echo $($1 -version 2>&1 | grep 'version' | awk -F '"' '{print $2}')
}
# Get HBase processes
_procs() {
    declare -A procs
    while IFS= read -r proc; do
        cmdline=$(echo $proc | awk '{for(i=11;i<=NF;++i) printf "%s ", $i; print ""}')
        if [[ $cmdline == *"$1"* && $cmdline != *"bash -c"* ]]; then
            hbase_home=$(re_search '(?<=-Dhbase.home.dir=)\S+' "$cmdline")
            install_path=$(realpath $hbase_home)
            log_path=$(readlink -f $(re_search '(?<=-Dhbase.log.dir=)\S+' "$cmdline"))
            config_dir=$(re_search '(?<=--config\s)\S+' "$cmdline")
            [[ -z $config_dir ]] && config_dir="$install_path/conf"
            config_file="$config_dir/hbase-site.xml"
            hbase_exe="$install_path/bin/hbase"
            [[ ! -f $hbase_exe ]] && hbase_exe=$(find $install_path -type f -name hbase -executable)
            [[ ! -f $hbase_exe ]] && { echo "{}"; exit 0; }
            java_path=$(echo $cmdline | awk '{print $1}')
            java_home=$(echo "$cmdline" | awk '{print $1}' | grep -oP '.*/(?=bin/java)')
            procs[$(echo $proc | awk '{print $2}')]=$hbase_exe'|'$install_path'|'$config_file'|'$java_path'|'$log_path'|'$java_home
        fi
    done < <(ps aux)
    echo "${procs[@]}"
}
# Convert XML to dict
xml_to_dict() {
    declare -A xml_dict
    while IFS= read -r line; do
        [[ $line =~ \<name\>(.*)\</name\> ]] && key=${BASH_REMATCH[1]}
        [[ $line =~ \<value\>(.*)\</value\> ]] && xml_dict[$key]=${BASH_REMATCH[1]}
    done < <(grep -E '<name>|<value>' "$1")
    echo $(declare -p xml_dict)
}
# Discover HBase master server
discover_hbase_masterserver() {
    procs=($(_procs 'org.apache.hadoop.hbase.master.HMaster'))
    for proc in "${procs[@]}"; do
        IFS='|' read -r hbase_exe install_path config_file java_path log_path java_home<<< "$proc"
        export JAVA_HOME=$java_home
        version=$(run_cmd "$hbase_exe version | grep ^HBase | awk '{print \$NF}'")
        port=16000
        eval $(xml_to_dict $config_file)
        tmp_dir=""
        cluster_distributed="false"
        unsafe_stream_capability_enforce="false"

        for key in "${!xml_dict[@]}"; do
            [[ $key == "hbase.master.port" ]] && port=${xml_dict[$key]}
            [[ $key == "hbase.cluster.distributed" ]] && cluster_distributed=${xml_dict[$key]}
            [[ $key == "hbase.tmp.dir" ]] && tmp_dir=${xml_dict[$key]}
            [[ $key == "hbase.unsafe.stream.capability.enforce" ]] && unsafe_stream_capability_enforce=${xml_dict[$key]}
        done
        [[ $tmp_dir == "./tmp" ]] && tmp_dir="/tmp"
        java_version=$(get_jdk_version $java_path)
        bk_inst_name="${bk_host_innerip}-hbase-${port}"
        json_template='{"inst_name":"%s","bk_obj_id":"hbase","ip_addr":"%s","port":"%s","install_path":"%s","version":"%s","log_path":"%s","config_file":"%s","tmp_dir":"%s","cluster_distributed":"%s","unsafe_stream_capability_enforce":"%s","java_path":"%s","java_version":"%s"}'
        echo $(printf "$json_template" "$bk_inst_name" "$bk_host_innerip" "$port" "$install_path" "$version" "$log_path" "$config_file" "$tmp_dir" "$cluster_distributed" "$unsafe_stream_capability_enforce" "$java_path" "$java_version")
        break
    done
}
main() {
    discover_hbase_masterserver
}
main "$@"
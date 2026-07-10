#!/bin/bash
# Phase 4 patch(2026-07-08):修 bk_host_innerip 模板替换 bug(同 Phase 3 memcached/haproxy 模式)
# 上游写死 bk_host_innerip={{bk_host_innerip}},runner 不替换;改 hostname 实际获取
# 同步策略:与 plugins/inputs/jboss/jboss_default_discover.sh 保持同步


bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

convert_bytes() {
    size_with_unit=$1
    target_unit=$2
    [ -z "$size_with_unit" ] && echo '' && return
    size=$(echo "$size_with_unit" | grep -oP '\d+(\.\d+)?')
    src_unit=$(echo "$size_with_unit" | grep -oP '[bkmgtpezyi]{1,3}' | tr '[:lower:]' '[:upper:]')
    case "$src_unit" in
        G|GB|GIB) factor=1024 ;;
        M|MB|MIB) factor=1 ;;
        K|KB|KIB) factor=0.0009765625 ;;
        *) factor=1 ;;
    esac
    printf "%.0f%s" "$(echo "$size * $factor" | bc -l)" "$target_unit"
}

re_search() {
    pattern=$1
    string=$2
    result=$(echo "$string" | grep -oP "$pattern")
    echo "$result"
}

discover_jboss() {
    pids=$(ps -ef | grep -v grep | grep 'jboss-modules.jar' | awk '{print $2}')
    [ -z "$pids" ] && echo "{}" && exit 0
    for pid in $pids; do
        cmdline=$(cat /proc/$pid/cmdline | tr '\0' ' ')
        jboss_home=$(re_search '(?<=-Djboss.home.dir=)\S+' "$cmdline")
        [ -z "$jboss_home" ] && continue
        user=$(ps -p $pid -o user= | xargs)
        jvm_xms=$(convert_bytes "$(re_search '(?<=-Xms)\S+' "$cmdline")" 'M')
        jvm_xmx=$(convert_bytes "$(re_search '(?<=-Xmx)\S+' "$cmdline")" 'M')
        role=''
        [[ "$cmdline" == *'org.jboss.as.server'* ]] && role='server'
        [[ "$cmdline" == *'org.jboss.as.host-controller'* ]] && role='host-controller'
        [[ "$cmdline" == *'org.jboss.as.standalone'* ]] && role='standalone'
        configfile_name=$(re_search '(?<=-Djboss.server.default.config=)\S+' "$cmdline")
        [ -n "$configfile_name" ] && config_file="$jboss_home/standalone/configuration/$configfile_name" || config_file="$jboss_home/standalone/configuration/standalone.xml"
        port=$(grep -oPm1 '(?<=socket-binding name="http" port="\$\{jboss.http.port:)\d+' "$config_file")
        [ -z "$port" ] && port=8080
        version_result=$(su - $user -c "$jboss_home/bin/standalone.sh --version" 2>/dev/null)
        version=$(echo "$version_result" | grep -oP '(?<=JBoss AS |WildFly Full )\d+(\.\d+)*' | head -1)
        bk_inst_name="${bk_host_innerip}-jboss-${role}-${port}"
        printf '{"bk_inst_name":"%s","bk_obj_id":"jboss","ip_addr":"%s","port":"%s","install_path":"%s","version":"%s","jvm_xms":"%s","jvm_xmx":"%s","role":"%s","config_file":"%s"}\n' \
            "$bk_inst_name" "$bk_host_innerip" "$port" "$jboss_home" "$version" "$jvm_xms" "$jvm_xmx" "$role" "$config_file"
    done
}

discover_jboss

#!/bin/bash

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
    pids=$(pgrep -f "ceph-mon|ceph-osd|ceph-mds|ceph-mgr")
    for pid in $pids; do
        exe=$(readlink -f /proc/$pid/exe)
        cmdline=$(ps -p $pid -o args=)
        role=$(ps -p $pid -o comm=)
        echo "$pid|$exe|$cmdline|$role"
    done
}

discover_ceph() {
    procs=$(_procs)
    [ -z "$procs" ] && echo "{}" && exit 0
    while IFS='|' read -r pid exe cmdline role; do
        ceph_exe=$(dirname "$exe")/ceph
        conf=$(re_search '(?<=--conf\s)\S+' "$cmdline")
        [ -z "$conf" ] && conf="/etc/ceph/ceph.conf"
        version=$(run_cmd "$ceph_exe version" | grep -oP '(?<=ceph version )\S+' | head -1)
        port=$(ss -ltnp | grep "$pid" | awk '{print $4}' | awk -F: '{print $NF}' | paste -sd '&' -)
        bk_inst_name="{{bk_host_innerip}}-$role-$port"
        install_path=$(dirname "$exe" | sed 's/\/bin//')
        printf '{"bk_inst_name":"%s","bk_obj_id":"ceph","ip_addr":"{{bk_host_innerip}}","port":"%s","version":"%s","role":"%s","install_path":"%s","config_file":"%s","cmdline":"%s","ceph_exe":"%s"}\n' \
            "$bk_inst_name" "$port" "$version" "$role" "$install_path" "$conf" "$cmdline" "$ceph_exe"
    done <<< "$procs"
}

discover_ceph

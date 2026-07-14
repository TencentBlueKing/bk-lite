#!/bin/bash
# Phase 4 patch(2026-07-08):修 bk_host_innerip 模板替换 bug(字符串字面 {bk_host_innerip})
# 上游在 printf 字符串里直接写 "{bk_host_innerip}",runner 不替换;改成 %s + 引用 $bk_host_innerip
# 同步策略:与 plugins/inputs/tuxedo/tuxedo_default_discover.sh 保持同步

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"


read_configfile() {
    configfile=$1
    grep -v '^\s*#' "$configfile" | grep -v '^\s*$' | xargs
}

discover_tuxedo() {
    pids=$(pgrep -f "BEA Tuxedo|tmboot|tlisten")
    if [ -z "$pids" ]; then
        echo "{}"
        exit 0
    fi

    for pid in $pids; do
        cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline)
        exe_path=$(readlink -f /proc/$pid/exe)
        install_path=$(dirname "$(dirname "$exe_path")")
        bin_path=$(dirname "$exe_path")
        tuxconfig=$(echo "$cmdline" | grep -oP '(?<=TUXCONFIG=)\S+' | head -1)
        conf_file=${tuxconfig:-"$install_path/ubbconfig"}
        config_data=$(read_configfile "$conf_file")
        ipckey=$(echo "$config_data" | grep -oP '(?<=IPCKEY=)[^ ]+' | head -1)
        domainid=$(echo "$config_data" | grep -oP '(?<=DOMAINID=)[^ ]+' | head -1)
        lmid=$(echo "$config_data" | grep -oP '(?<=LMID=)[^ ]+' | head -1)
        patch_level=$(tmadmin -v 2>/dev/null | grep -oP '(?<=Patch Level )\S+' | head -1)
        version=$(tmadmin -v 2>/dev/null | grep -oP '(?<=Version )\S+' | head -1)
        maxdispatchthreads=$(echo "$config_data" | grep -oP '(?<=MAXDISPATCHTHREADS=)\d+' | head -1)
        mindispatchthreads=$(echo "$config_data" | grep -oP '(?<=MINDISPATCHTHREADS=)\d+' | head -1)
        port=$(ss -ltnp | grep "$pid" | awk '{print $4}' | awk -F: '{print $NF}' | paste -sd '&' -)
        bk_inst_name="$bk_host_innerip-tuxedo-${ipckey:-$pid}"
        printf '{"bk_inst_name":"%s","bk_obj_id":"tuxedo","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","bin_path":"%s","conf_file":"%s","domainid":"%s","ipckey":"%s","lmid":"%s","patch_level":"%s","maxdispatchthreads":"%s","mindispatchthreads":"%s"}\n' \
            "$bk_inst_name" "$bk_host_innerip" "$port" "$version" "$install_path" "$bin_path" "$conf_file" "$domainid" "$ipckey" "$lmid" "$patch_level" "$maxdispatchthreads" "$mindispatchthreads"
    done
}

discover_tuxedo

#!/bin/bash
# Oscar (神通数据库) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 Oscar 安装(国产 binary,需 amd64 CI + license)
# 进程名:oscardb / oscar
# 默认端口:2003 (OSCAR)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 Oscar 进程(oscar*)
oscar_pids=$(ps -ef | grep -E '[o]scar' | grep -v 'grep' | awk '{print $2}')
if [ -z "$oscar_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $oscar_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/oscar"

    version=$($install_path/bin/oscar --version 2>&1 | head -1 | tr -d '\r\n')
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-oscar-2003"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"oscar","port":"2003","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
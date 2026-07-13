#!/bin/bash
# Sybase (SAP 数据库) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 SAP Sybase ASE 安装(需 amd64 CI + license)
# Sybase ASE = Adaptive Server Enterprise
# 进程名: dataserver (Sybase 主进程)
# 默认端口:5000 (ASE listener)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 Sybase 进程
sybase_pids=$(ps -ef | grep -E '[d]ataserver|[S]ybase' | grep -v 'grep' | awk '{print $2}')
if [ -z "$sybase_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $sybase_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/sybase"

    version=$($install_path/OCS-16_0/bin/isql -Usa -P -SASE 2>&1 | head -1 | grep -oE 'Adaptive Server Enterprise[ /][0-9.x]+' | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-sybase-5000"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"sybase","port":"5000","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
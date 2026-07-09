#!/bin/bash
# TongLINK/Q (东方通消息中间件) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 TongLINK/Q 安装(国产 binary,需 amd64 CI + license)
# 进程名:tlq_agent / TongLINK
# 默认端口:10260 (TLQ 主端口)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 TongLINK 进程
tlq_pids=$(ps -ef | grep -E '[t]lq|[T]ongLINK' | grep -v 'grep' | awk '{print $2}')
if [ -z "$tlq_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $tlq_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/TongLINK"

    # 版本从 product.info 读
    version_file="${install_path}/conf/product.info"
    [ -f "$version_file" ] && version=$(grep -oE 'VERSION[ ]*=[ ]*[0-9.]+' "$version_file" | cut -d= -f2 | tr -d ' ')
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-tonglinkq-10260"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"tonglinkq","port":"10260","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
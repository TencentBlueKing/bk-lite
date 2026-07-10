#!/bin/bash
# TongGTP (东方通数据传输平台) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 TongGTP 安装(国产 binary,需 amd64 CI + license)
# TongGTP 是东方通数据传输中间件(基于 TongLINK/Q 之上)
# 默认端口:8090 (HTTP)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 TongGTP 进程
gtp_pids=$(ps -ef | grep -E '[T]ongGTP|[g]tp' | grep -v 'grep' | awk '{print $2}')
if [ -z "$gtp_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $gtp_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/TongGTP"

    version=$(grep -oE 'TongGTP[ -][0-9.]+' "$install_path/conf/version.cfg" 2>/dev/null | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-tonggtp-8090"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"tonggtp","port":"8090","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
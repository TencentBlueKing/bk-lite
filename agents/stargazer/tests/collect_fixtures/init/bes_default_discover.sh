#!/bin/bash
# BES (国产中间件) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# BES = Big Event Server / 蓝鲸基础平台事件服务(国产中间件)
# 真实采集依赖 BES 安装(国产 binary,需 amd64 CI + license)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 BES 进程
bes_pids=$(ps -ef | grep -E '[b]es\.server|[B]igEventServer' | awk '{print $2}')
if [ -z "$bes_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $bes_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/bes"

    version=$(grep -oE 'BES[ -][0-9.]+' "$install_path/conf/version.info" 2>/dev/null | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-bes-9090"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"bes","port":"9090","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
#!/bin/bash
# GBase8s (南大通用数据库) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 GBase8s 安装(国产 binary,需 amd64 CI + license)
# 进程名:oninit (GBase 共享内存初始化进程)
# 默认端口:9088 (SQLI)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 GBase 进程(oninit)
gbase_pids=$(ps -ef | grep -E '[o]ninit|[o]nstat' | awk '{print $2}')
if [ -z "$gbase_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $gbase_pids; do
    # 版本信息(GBase -V)
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/gbase8s"

    version=$($install_path/bin/onstat - 2>/dev/null | head -1 | grep -oE 'GBase[ -][A-Za-z0-9. -]+' | head -1)
    [ -z "$version" ] && version="(unknown)"

    # 监听端口
    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-gbase8s-9088"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"gbase8s","port":"9088","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
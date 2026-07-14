#!/bin/bash
# Informix (IBM 数据库) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 IBM Informix 安装(需 amd64 CI + license)
# 进程名:oninit (Informix 共享内存初始化进程)
# 默认端口:9088 (SQLI 协议,Informix 同 GBase)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 Informix 进程
informix_pids=$(ps -ef | grep -E '[o]ninit|[i]nformix' | grep -v 'grep' | awk '{print $2}')
if [ -z "$informix_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $informix_pids; do
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    install_path=$(dirname $(dirname "$exe"))
    [ -z "$install_path" ] && install_path="/opt/informix"

    version=$($install_path/bin/onstat - 2>/dev/null | head -1 | grep -oE 'Informix[ -][0-9.]+' | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-informix-9088"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"informix","port":"9088","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
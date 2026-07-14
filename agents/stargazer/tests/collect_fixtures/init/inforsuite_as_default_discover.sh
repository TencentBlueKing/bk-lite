#!/bin/bash
# InforSuite AS (中创应用服务器) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 InforSuite 安装(国产 binary,需 amd64 CI + license)
# 中创股份 InforSuite 应用服务器(类 WebLogic/WebSphere)
# 进程名:java (InforSuite 启动的 JVM)
# 默认端口:8080 (HTTP)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 InforSuite JVM
inforsuite_pids=$(ps -ef | grep '[I]nforSuite' | grep java | awk '{print $2}')
if [ -z "$inforsuite_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $inforsuite_pids; do
    cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    install_path=$(echo "$cmdline" | grep -oE '/[^ ]*[Ii]nforSuite[^ ]*' | head -1)
    [ -z "$install_path" ] && install_path="/opt/InforSuite"

    version_file=$(find "$install_path" -name "VERSION*" -type f 2>/dev/null | head -1)
    [ -n "$version_file" ] && version=$(cat "$version_file" | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-inforsuite_as-8080"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"inforsuite_as","port":"8080","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
#!/bin/bash
# Apusic (东方通应用服务器) 采集脚本 — G5.1 占位
# -----------------------------------------------------------------------------
# 真实采集依赖 Apusic 安装(国产 binary,需 amd64 CI + license)
# Apusic 是东方通 Java EE 应用服务器(类 WebLogic/WebSphere)
# 进程名:java (Apusic 启动的 JVM)
# 默认端口:6888 (HTTP 管理)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# 探测 Apusic JVM(进程 cmdline 含 Apusic)
apusic_pids=$(ps -ef | grep '[A]pusic' | grep java | awk '{print $2}')
if [ -z "$apusic_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $apusic_pids; do
    cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)

    # 安装路径(从 cmdline 找)
    install_path=$(echo "$cmdline" | grep -oE '/[^ ]*Apusic[^ ]*' | head -1)
    [ -z "$install_path" ] && install_path="/opt/apusic"

    # 版本从 VERSION 文件读
    version_file=$(find "$install_path" -name "VERSION*" -type f 2>/dev/null | head -1)
    [ -n "$version_file" ] && version=$(cat "$version_file" | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    bk_inst_name="$bk_host_innerip-apusic-6888"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"apusic","port":"6888","version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$version" "$install_path" "$listening" "$pid"
done
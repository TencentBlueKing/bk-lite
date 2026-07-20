#!/bin/bash
# Mycat 采集 wrapper（G5.1.1, 2026-07-08）
# -----------------------------------------------------------------------------
# 真实采集逻辑:检测 mycat 进程 + 端口 + JDK version + install_path
# mycat 1.6 是 Java 应用,通过 wrapper 启动,采集脚本与 kafka 模式类似
# 注:mycat 1.6 没有 CLI 工具,只能通过 ps/netstat 采集
# 简化:本副本不依赖 mycat 默认 collect 脚本(本来就没有),从零写
# 同步策略:无 upstream 可同步,本文件是 G5.1.1 新建

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip=$(hostname -i 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

discover_mycat() {
    # 找 mycat 进程（wrapper 启动的 JVM,cmdline 含 Mycat 或 mycat)
    mycat_pids=$(ps -ef | grep -E '[M]ycat|mycat' | grep -v grep | awk '{print $2}')
    if [ -z "$mycat_pids" ]; then
        echo "{}"
        exit 0
    fi
    for pid in $mycat_pids; do
        # cmdline
        cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
        [ -z "$cmdline" ] && cmdline=$(ps -p "$pid" -o args= 2>/dev/null)

        # 排除 grep / bash 自身
        echo "$cmdline" | grep -qE 'bash|grep' && continue

        # version(mycat 1.6 没有 --version,从 VERSION.txt 读)
        install_path="/opt/mycat"
        [ -f "$install_path/VERSION.txt" ] && version=$(cat "$install_path/VERSION.txt" | head -1 | tr -d '\r\n')
        [ -z "$version" ] && version="1.6.7.5"

        # 监听端口
        listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',')
        listening=$(echo "$listening" | sed 's/,$//')

        # JDK version
        jdk_version=$(java -version 2>&1 | head -1 | awk -F\" '{print $2}')

        bk_inst_name="$bk_host_innerip-mycat-8066"
        printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"mycat","port":"8066","mgt_port":"9066","version":"%s","jdk_version":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
            "$bk_inst_name" "$bk_host_innerip" "$version" "$jdk_version" "$install_path" "$listening" "$pid"
    done
}

discover_mycat

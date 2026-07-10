#!/bin/bash
# Storm (Apache Storm Nimbus) 采集脚本 — G5.3 占位
# -----------------------------------------------------------------------------
# 集群降级方案:单节点伪分布式 Nimbus + Supervisor
# Web UI 默认端口:8080 (Storm UI)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

storm_home="${STORM_HOME:-/opt/storm}"
storm_ui_port=8080

# 探测 Storm Nimbus/Supervisor 进程
storm_pids=$(ps -ef | grep -E '[N]imbus|[S]upervisor|storm.daemon' | awk '{print $2}')
if [ -z "$storm_pids" ]; then
    echo "{}"
    exit 0
fi

# 取主进程(优先级:nimbus > supervisor)
main_pid=""
for pid in $storm_pids; do
    cmdline=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null)
    if echo "$cmdline" | grep -q 'nimbus'; then
        main_pid=$pid
        role="nimbus"
        break
    fi
done
[ -z "$main_pid" ] && main_pid=$(echo "$storm_pids" | head -1)
[ -z "$role" ] && role="supervisor"

version=$($storm_home/bin/storm version 2>/dev/null | head -1)
[ -z "$version" ] && version="(unknown)"

listening=$(ss -tlnp 2>/dev/null | grep "pid=$main_pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

# topology 数量
topology_count=$(curl -s --max-time 5 "http://localhost:${storm_ui_port}/api/v1/topology/summary" 2>/dev/null | grep -oE '"topologies":[0-9]*' | head -1 | cut -d: -f2)
[ -z "$topology_count" ] && topology_count="0"

bk_inst_name="$bk_host_innerip-storm-${storm_ui_port}"
printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"storm","role":"%s","port":"%s","version":"%s","topology_count":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
    "$bk_inst_name" "$bk_host_innerip" "$role" "$storm_ui_port" "$version" "$topology_count" "$storm_home" "$listening" "$main_pid"
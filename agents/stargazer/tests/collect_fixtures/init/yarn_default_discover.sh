#!/bin/bash
# YARN (Hadoop YARN ResourceManager) 采集脚本 — G5.3 占位
# -----------------------------------------------------------------------------
# 集群降级方案:单节点伪分布式 ResourceManager
# Web UI 默认端口:8088 (YARN Web UI)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

hadoop_home="${HADOOP_HOME:-/opt/hadoop}"
rm_web_port=8088

# 探测 ResourceManager 进程
rm_pids=$(ps -ef | grep -E '[R]esourceManager' | awk '{print $2}')
if [ -z "$rm_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $rm_pids; do
    version=$($hadoop_home/bin/yarn version 2>/dev/null | head -1)
    [ -z "$version" ] && version="(unknown)"

    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    # 集群节点数(从 REST API 拿)
    node_count=$(curl -s --max-time 5 "http://localhost:${rm_web_port}/ws/v1/cluster/nodes" 2>/dev/null | grep -oE '"total":[0-9]+' | head -1 | cut -d: -f2)
    [ -z "$node_count" ] && node_count="0"

    bk_inst_name="$bk_host_innerip-yarn-${rm_web_port}"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"yarn","port":"%s","version":"%s","node_count":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$rm_web_port" "$version" "$node_count" "$hadoop_home" "$listening" "$pid"
done
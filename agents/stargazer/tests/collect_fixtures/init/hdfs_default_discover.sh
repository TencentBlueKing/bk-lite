#!/bin/bash
# HDFS (Hadoop HDFS NameNode) 采集脚本 — G5.3 占位
# -----------------------------------------------------------------------------
# 集群降级方案:单节点伪分布式 NameNode
# 真实采集依赖 hadoop 安装(需 amd64 CI)
# Web UI 默认端口:9870 (HDFS NameNode Web UI)
# -----------------------------------------------------------------------------
set -e

bk_host_innerip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$bk_host_innerip" ] && bk_host_innerip="127.0.0.1"

# HDFS 路径
hadoop_home="${HADOOP_HOME:-/opt/hadoop}"
nn_web_port=9870

# 探测 NameNode 进程
nn_pids=$(ps -ef | grep -E '[N]ameNode' | awk '{print $2}')
if [ -z "$nn_pids" ]; then
    echo "{}"
    exit 0
fi

for pid in $nn_pids; do
    # 版本从 NameNode log 拿
    version_file="$hadoop_home/logs/hadoop-*-namenode-*.log"
    version=$(grep -oE 'Hadoop[ /][0-9.]+' $version_file 2>/dev/null | head -1)
    [ -z "$version" ] && version=$($hadoop_home/bin/hdfs version 2>/dev/null | head -1)

    # 监听端口(NameNode RPC + Web UI)
    listening=$(ss -tlnp 2>/dev/null | grep "pid=$pid," | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ',' | sed 's/,$//')

    # 集群名(从 hdfs-site.xml 拿)
    cluster_name=$(xmllint --xpath '//property[name="dfs.nameservices"]/value/text()' "$hadoop_home/etc/hadoop/hdfs-site.xml" 2>/dev/null)
    [ -z "$cluster_name" ] && cluster_name="(default)"

    bk_inst_name="$bk_host_innerip-hdfs-${nn_web_port}"
    printf '{"bk_inst_name":"%s","ip_addr":"%s","bk_obj_id":"hdfs","port":"%s","version":"%s","cluster_name":"%s","install_path":"%s","listening_ports":"%s","pid":%s}\n' \
        "$bk_inst_name" "$bk_host_innerip" "$nn_web_port" "$version" "$cluster_name" "$hadoop_home" "$listening" "$pid"
done
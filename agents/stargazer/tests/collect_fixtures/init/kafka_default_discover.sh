#!/bin/bash
# kafka 采集脚本 — 用 kafka-topics.sh 拉集群 / topic 信息,输出 JSON dict
# KRaft 模式,单 broker
set -e

host_innerip=$(hostname -I | awk '{print $1}')
kafka_port=9092
kafka_bootstrap="localhost:${kafka_port}"
kafka_home="/opt/kafka"

# Kafka 是 JVM 进程,/proc/pid/exe 是 java;硬编码 launcher 路径
bin_path="${kafka_home}/bin"
config_path="${kafka_home}/config/kraft/server.properties"

kafka_pid=$(pgrep -f "kafka.Kafka" | head -1)
kafka_user="root"

# version: kafka-topics.sh --version 输出 "3.6.0 (Commit:...)"
version=$(/opt/kafka/bin/kafka-topics.sh --version 2>&1 | awk '{print $1}' | head -1)

# topic 列表(给 15s 超时)
topics=$(timeout 15 /opt/kafka/bin/kafka-topics.sh --bootstrap-server "${kafka_bootstrap}" --list --timeout 10000 2>/dev/null | grep -v '^Error' | sort | tr '\n' ',' | sed 's/,$//')
if [[ -z "$topics" || "$topics" == *"Error"* ]]; then
    topics="(empty or query failed)"
fi

# cluster id — 从 server.properties 拿 process.roles / node.id 不可靠,改从 kafka-storage.sh 输出
# 或从 __cluster_metadata 内部 topic 的 metadata 推断。最稳定的是从 server log 拿
# fallback: kafka-storage.sh info 看 log 目录
cluster_id=$(grep -oP 'Cluster ID:\s*\K\S+' /opt/kafka/logs/server.log 2>/dev/null | tail -1)
if [[ -z "$cluster_id" ]]; then
    cluster_id=$(grep -oP 'clusterId[= ]\K\S+' /opt/kafka/logs/server.log 2>/dev/null | head -1)
fi
if [[ -z "$cluster_id" ]]; then
    cluster_id="(unparsed)"
fi

# broker count (从 server.log 看 "started" 行)
broker_count=$(grep -c 'KafkaServer id=' /opt/kafka/logs/server.log 2>/dev/null | head -1)
if [[ -z "$broker_count" ]]; then
    broker_count="0"
fi

inst_name="${host_innerip}-kafka-${kafka_port}"

cat <<EOF
{"inst_name":"${inst_name}","ip_addr":"${host_innerip}","obj_id":"kafka","port":"${kafka_port}","version":"${version}","cluster_id":"${cluster_id}","broker_count":"${broker_count}","topics":"${topics}","bin_path":"${bin_path}","config":"${config_path}","user":"${kafka_user}","pid":"${kafka_pid}"}
EOF
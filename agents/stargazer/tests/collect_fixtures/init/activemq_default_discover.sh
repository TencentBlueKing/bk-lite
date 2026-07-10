#!/bin/bash
# activemq 采集脚本 — 拉 activemq 进程 / 端口 / 配置信息,输出 JSON dict
set -e

host_innerip=$(hostname -I | awk '{print $1}')
amq_port=61616
web_port=8161
amq_home="/usr/share/activemq"

# activemq 进程(Java)
amq_pid=$(pgrep -f "activemq.jar" | head -1)
if [[ -z "$amq_pid" ]]; then
    amq_pid=$(pgrep -f "org.apache.activemq" | head -1)
fi

bin_path="/usr/bin"  # /usr/bin/activemq 是 ubuntu apt 装包的入口
config_path="${amq_home}/conf/activemq.xml"
amq_user="activemq"

# version (从 jar 内的 manifest / 文件名)
version="unknown"
if [[ -d "${amq_home}/lib" ]]; then
    # activemq 5.x 包,version 在 jar 文件名里
    version=$(ls ${amq_home}/lib/activemq-*.jar 2>/dev/null | head -1 | grep -oP 'activemq-(?:core-|karaf-|)[\d.]+' | head -1 | sed 's/^activemq-//' | sed 's/-core//' | sed 's/-karaf//')
fi
if [[ "$version" == "unknown" ]] || [[ -z "$version" ]]; then
    # dpkg query 兜底
    version=$(dpkg-query -W -f='${Version}' activemq 2>/dev/null | head -1)
fi

# web console 是否可达
web_reachable="false"
if curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${web_port}/admin/" 2>/dev/null; then
    web_reachable="true"
fi

# 监听端口(从 ss 取)
listening_ports=$(ss -tln | grep -E ':(61616|8161|5672|61613|1883|61617) ' | awk '{print $4}' | awk -F ':' '{print $NF}' | sort -u | tr '\n' ',' | sed 's/,$//')

inst_name="${host_innerip}-activemq-${amq_port}"

cat <<EOF
{"inst_name":"${inst_name}","ip_addr":"${host_innerip}","obj_id":"activemq","port":"${amq_port}","web_port":"${web_port}","web_reachable":"${web_reachable}","version":"${version}","listening_ports":"${listening_ports}","bin_path":"${bin_path}","config":"${config_path}","user":"${amq_user}","pid":"${amq_pid}"}
EOF
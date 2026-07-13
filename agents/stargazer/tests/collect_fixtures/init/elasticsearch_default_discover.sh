#!/bin/bash
# elasticsearch 采集脚本 — 通过 ES REST API 拉集群信息,输出 JSON dict
# 设计:参考 mongodb/nginx 等的 _default_discover.sh,单行 JSON,所有字段靠 curl 拉
set -e

host_innerip=$(hostname -I | awk '{print $1}')
es_port=9200
es_url="http://127.0.0.1:${es_port}"

# root info: cluster_name, version, lucene_version
root_json=$(curl -fsS "${es_url}/" 2>/dev/null || echo '{}')
cluster_name=$(echo "$root_json" | grep -oP '"cluster_name"\s*:\s*"\K[^"]+' | head -1)
version=$(echo "$root_json" | grep -oP '"number"\s*:\s*"\K[^"]+' | head -1)
lucene_version=$(echo "$root_json" | grep -oP '"lucene_version"\s*:\s*"\K[^"]+' | head -1)
build_flavor=$(echo "$root_json" | grep -oP '"build_flavor"\s*:\s*"\K[^"]+' | head -1)

# cluster health: status, node count, shard count
health_json=$(curl -fsS "${es_url}/_cluster/health" 2>/dev/null || echo '{}')
status=$(echo "$health_json" | grep -oP '"status"\s*:\s*"\K[^"]+' | head -1)
node_count=$(echo "$health_json" | grep -oP '"number_of_nodes"\s*:\s*\K[0-9]+' | head -1)
active_shards=$(echo "$health_json" | grep -oP '"active_shards"\s*:\s*\K[0-9]+' | head -1)
unassigned_shards=$(echo "$health_json" | grep -oP '"unassigned_shards"\s*:\s*\K[0-9]+' | head -1)

# 节点 / 进程信息
# ES 8.x 是 JVM 进程,/proc/pid/exe 是 java,不是 elasticsearch。
# 直接硬编码 launcher 路径(已知布局,跨 ES 小版本稳定)。
bin_path="/usr/share/elasticsearch/bin"
es_user="elasticsearch"
es_pid=$(pgrep -f "org.elasticsearch.bootstrap.Elasticsearch" | head -1)
config_path="/etc/elasticsearch/elasticsearch.yml"

inst_name="${host_innerip}-elasticsearch-${es_port}"

cat <<EOF
{"inst_name":"${inst_name}","ip_addr":"${host_innerip}","obj_id":"elasticsearch","port":"${es_port}","version":"${version}","lucene_version":"${lucene_version}","build_flavor":"${build_flavor}","cluster_name":"${cluster_name}","status":"${status}","number_of_nodes":"${node_count}","active_shards":"${active_shards}","unassigned_shards":"${unassigned_shards}","bin_path":"${bin_path}","config":"${config_path}","user":"${es_user}","pid":"${es_pid}"}
EOF
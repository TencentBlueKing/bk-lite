import os

# victoriametrics服务信息
VICTORIAMETRICS_HOST = os.getenv("VICTORIAMETRICS_HOST")
VICTORIAMETRICS_USER = os.getenv("VICTORIAMETRICS_USER")
VICTORIAMETRICS_PWD = os.getenv("VICTORIAMETRICS_PWD")

# 内置的监控对象
MONITOR_OBJS = [
    {
        "type": "OS",
        "name": "Host",
        "default_metric": 'any({instance_type="os"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["cpu_summary.usage", "mem.pct_used", "load5"],
    },
    {
        "type": "Web",
        "name": "Website",
        "default_metric": 'any({instance_type="web"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["http_duration", "http_success.rate", "http_code"],
    },
    {
        "type": "Web",
        "name": "Ping",
        "default_metric": 'any({instance_type="ping"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["ping_response_time", "ping_error_response_code"],
    },
    {
        "type": "Network Device",
        "name": "Switch",
        "default_metric": 'any({instance_type="switch"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Network Device",
        "name": "Router",
        "default_metric": 'any({instance_type="router"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Network Device",
        "name": "Firewall",
        "default_metric": 'any({instance_type="firewall"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Network Device",
        "name": "Loadbalance",
        "default_metric": 'any({instance_type="loadbalance"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Network Device",
        "name": "Detection Device",
        "default_metric": 'any({instance_type="detection_device"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Network Device",
        "name": "Scanning Device",
        "default_metric": 'any({instance_type="scanning_device"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Hardware Device",
        "name": "Bastion Host",
        "default_metric": 'any({instance_type="bastion_host"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Hardware Device",
        "name": "Storage",
        "default_metric": 'any({instance_type="storage"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "Hardware Device",
        "name": "Hardware Server",
        "default_metric": 'any({instance_type="hardware_server"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["sysUpTime", "iftotalInOctets", "iftotalOutOctets"],
    },
    {
        "type": "K8S",
        "name": "Cluster",
        "default_metric": 'any({instance_type="k8s"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["cluster_pod_count", "cluster_node_count"],
    },
    {
        "type": "K8S",
        "name": "Pod",
        "default_metric": 'prometheus_remote_write_kube_pod_info',
        "instance_id_keys": ["instance_id", "pod"],
        "supplementary_indicators": ["pod_status", "pod_cpu_utilization","pod_memory_utilization"],
    },
    {
        "type": "K8S",
        "name": "Node",
        "default_metric": 'prometheus_remote_write_kube_node_info',
        "instance_id_keys": ["instance_id", "node"],
        "supplementary_indicators": ["node_status_condition", "node_cpu_utilization", "node_memory_utilization"],
    },
    {
        "type": "Other",
        "name": "SNMP Trap",
        "default_metric": 'any({instance_type="snmp_trap"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": [],
    },
    {
        "type": "Middleware",
        "name": "RabbitMQ",
        "default_metric": 'any({instance_type="rabbitmq"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["rabbitmq_overview_messages_ready"],
    },
    {
        "type": "Middleware",
        "name": "Nginx",
        "default_metric": 'any({instance_type="nginx"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["nginx_requests", "nginx_active"],
    },
    {
        "type": "Middleware",
        "name": "Zookeeper",
        "default_metric": 'any({instance_type="zookeeper"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["zookeeper_uptime", "zookeeper_avg_latency"],
    },
    {
        "type": "Middleware",
        "name": "ActiveMQ",
        "default_metric": 'any({instance_type="activemq"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["activemq_topic_consumer_count"],
    },
    {
        "type": "Middleware",
        "name": "Apache",
        "default_metric": 'any({instance_type="apache"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["apache_uptime", "apache_req_per_sec", "apache_cpu_load"],
    },
    {
        "type": "Middleware",
        "name": "ClickHouse",
        "default_metric": 'any({instance_type="clickhouse"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["clickhouse_events_query", "clickhouse_events_inserted_rows", "clickhouse_asynchronous_metrics_load_average1"],
    },
    {
        "type": "Middleware",
        "name": "Consul",
        "default_metric": 'any({instance_type="consul"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["consul_health_checks_status", "consul_health_checks_passing"],
    },
    {
        "type": "Middleware",
        "name": "Tomcat",
        "default_metric": 'any({instance_type="tomcat"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["tomcat_connector_request_count", "tomcat_connector_current_threads_busy", "tomcat_connector_error_count"],
    },
    {
        "type": "Container Management",
        "name": "Docker",
        "default_metric": 'any({instance_type="docker"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["docker_n_containers"],
    },
    {
        "type": "Container Management",
        "name": "Docker Container",
        "default_metric": 'docker_container_mem_usage',
        "instance_id_keys": ["instance_id", "container_name"],
        "supplementary_indicators": ["docker_container_status", "docker_container_cpu_usage_percent", "docker_container_mem_usage_percent"],
    },
    {
        "type": "Database",
        "name": "ElasticSearch",
        "default_metric": 'any({instance_type="elasticsearch"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["elasticsearch_fs_total_available_in_bytes", "elasticsearch_http_current_open", "elasticsearch_indices_docs_count"],
    },
    {
        "type": "Database",
        "name": "Mysql",
        "default_metric": 'any({instance_type="mysql"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["mysql_bytes_received", "mysql_bytes_sent", "mysql_connections_total"],
    },
    {
        "type": "Database",
        "name": "MongoDB",
        "default_metric": 'any({instance_type="mongodb"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["mongodb_connections_current", "mongodb_latency_commands", "mongodb_resident_megabytes"],
    },
    {
        "type": "Database",
        "name": "Redis",
        "default_metric": 'any({instance_type="redis"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["redis_used_memory", "redis_instantaneous_ops_per_sec"],
    },
    {
        "type": "Database",
        "name": "Postgres",
        "default_metric": 'any({instance_type="postgres"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["postgresql_active_time", "postgresql_blks_hit"],
    },
    {
        "type": "VMWare",
        "name": "vCenter",
        "default_metric": 'any({instance_type="vmware"}) by (instance_id)',
        "instance_id_keys": ["instance_id"],
        "supplementary_indicators": ["vmware_esxi_count", "vmware_datastore_count", "vmware_vm_count"],
    },
    {
        "type": "VMWare",
        "name": "ESXI",
        "default_metric": 'any({resource_type="vmware_esxi"}) by (instance_id, resource_id)',
        "instance_id_keys": ["instance_id", "resource_id"],
        "supplementary_indicators": ["esxi_cpu_usage_average_gauge", "esxi_mem_usage_average_gauge", "esxi_disk_read_average_gauge"],
    },
    {
        "type": "VMWare",
        "name": "VM",
        "default_metric": 'any({resource_type="vmware_vm"}) by (instance_id, resource_id)',
        "instance_id_keys": ["instance_id", "resource_id"],
        "supplementary_indicators": ["vm_cpu_usage_average_gauge", "vm_mem_usage_average_gauge", "vm_disk_io_usage_gauge"],
    },
    {
        "type": "VMWare",
        "name": "DataStorage",
        "default_metric": 'any({resource_type="vmware_ds"}) by (instance_id, resource_id)',
        "instance_id_keys": ["instance_id", "resource_id"],
        "supplementary_indicators": ["data_storage_disk_used_average_gauge", "data_storage_store_accessible_gauge"],
    },
]

# 阀值对比方法
THRESHOLD_METHODS = {
    ">": lambda x, y: x > y,
    "<": lambda x, y: x < y,
    "=": lambda x, y: x == y,
    "!=": lambda x, y: x != y,
    ">=": lambda x, y: x >= y,
    "<=": lambda x, y: x <= y,
}

# 告警等级权重
LEVEL_WEIGHT = {
    "warning": 2,
    "error": 3,
    "critical": 4,
    "no_data": 5,
}

# 对象顺序key
OBJ_ORDER = "OBJ_ORDER"

STARGAZER_URL = os.getenv("STARGAZER_URL", "http://stargazer:8083")

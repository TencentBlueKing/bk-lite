"""CMDB ↔ 监控对象映射：同步名单与 ingest 共用一张表。

只收能一对一落到现有监控插件对象的模型；无对应对象（WebLogic/存储/云账号等）不进表。
本模块不得 import monitor ingest 或 cmdb services，避免循环依赖。
"""

CMDB_MODEL_TO_MONITOR_OBJECT = {
    "host": "Host",
    "switch": "Switch",
    "router": "Router",
    "firewall": "Firewall",
    "loadbalance": "Loadbalance",
    "physcial_server": "Hardware Server",
    "mysql": "Mysql",
    "postgresql": "Postgres",
    "mssql": "MSSQL",
    "influxdb": "InfluxDB",
    "oracle": "Oracle",
    "redis": "Redis",
    "mongodb": "MongoDB",
    "es": "ElasticSearch",
    "apache": "Apache",
    "tomcat": "Tomcat",
    "nginx": "Nginx",
    "rabbitmq": "RabbitMQ",
    "kafka": "Kafka",
    "zookeeper": "Zookeeper",
    "activemq": "ActiveMQ",
    "minio": "Minio",
    "etcd": "Etcd",
    "haproxy": "Haproxy",
    "docker": "Docker Container",
}

CMDB_MONITOR_SYNC_MODEL_IDS = frozenset(CMDB_MODEL_TO_MONITOR_OBJECT)

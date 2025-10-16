class MonitorObjConstants:
    """监控实例相关常量"""

    # 监控对象关键字段
    OBJ_KEYS = ["name", "type", "default_metric", "instance_id_keys", "supplementary_indicators"]

    # 对象顺序key
    OBJ_ORDER = "OBJ_ORDER"

    # 对象默认顺序
    DEFAULT_OBJ_ORDER = [
        {"name_list": ["Host"], "type": "OS"},
        {"name_list": ["Website", "Ping"], "type": "Web"},
        {"name_list": ["ElasticSearch", "Mongodb", "Mysql", "Postgres", "Redis", "Oracle"], "type": "Database"},
        {"name_list": ["RabbitMQ", "Nginx", "Apache", "ClickHouse", "Consul", "Tomcat", "Zookeeper", "ActiveMQ", "MinIO", "Jetty", "WebLogic"], "type": "Middleware"},
        {"name_list": ["Switch", "Router", "Firewall", "Loadbalance", "Detection Device", "Scanning Device"], "type": "Network Device"},
        {"name_list": ["Bastion Host", "Storage", "Hardware Server"], "type": "Hardware Device"},
        {"name_list": ["Docker", "Docker Container"], "type": "Container Management"},
        {"name_list": ["Cluster", "Pod", "Node"], "type": "K8S"},
        {"name_list": ["vCenter", "ESXI", "VM", "DataStorage"], "type": "VMWare"},
        {"name_list": ["TCP", "CVM"], "type": "Tencent Cloud"},
        {"name_list": ["JVM", "SNMP Trap"], "type": "Other"}
    ]

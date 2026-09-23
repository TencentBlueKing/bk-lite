class MonitorObjConstants:
    """监控实例相关常量"""

    INSTANCE_ID_MAX_LENGTH = 200
    INSTANCE_NAME_MAX_LENGTH = 200

    # 监控对象关键字段
    OBJ_KEYS = ["name", "type", "default_metric", "instance_id_keys", "supplementary_indicators", "display_fields"]

    # 对象默认顺序
    DEFAULT_OBJ_ORDER = [
        {"name_list": ["Host"], "type": "OS"},
        {"name_list": ["Website", "Ping"], "type": "Web"},
        {"name_list": ["ElasticSearch", "InfluxDB", "MongoDB", "Mysql", "Postgres", "Redis", "Oracle"], "type": "Database"},
        {
            "name_list": [
                "RabbitMQ",
                "Nginx",
                "Apache",
                "Haproxy",
                "ClickHouse",
                "Consul",
                "Etcd",
                "Tomcat",
                "Active Directory",
                "Exchange",
                "Zookeeper",
                "ActiveMQ",
                "MinIO",
                "Jetty",
                "WebLogic",
            ],
            "type": "Middleware",
        },
        {
            "name_list": ["VLLM", "SGLang", "LlamaServer"],
            "type": "LLM Inference",
        },
        {
            "name_list": [
                "Switch",
                "Router",
                "Firewall",
                "Loadbalance",
                "Wanopt",
                "Detection Device",
                "Scanning Device",
                "Cisco Meraki",
                "Meraki Network",
                "Meraki Device",
                "Meraki Wireless AP",
                "Meraki Switch",
                "Meraki Appliance",
            ],
            "type": "Network Device",
        },
        {"name_list": ["Bastion Host", "Storage", "Hardware Server"], "type": "Hardware Device"},
        {"name_list": ["Docker", "Docker Container"], "type": "Container Management"},
        {"name_list": ["Cluster", "Pod", "Node"], "type": "K8S"},
        {"name_list": ["vCenter", "ESXI", "VM", "DataStorage"], "type": "VMWare"},
        {
            "name_list": [
                "SangforSCP",
                "SangforSCPHost",
                "SangforSCPVM",
                "CNware",
                "CNwareHost",
                "CNwareVM",
            ],
            "type": "Cloud",
        },
        {"name_list": ["TCP", "CVM"], "type": "Tencent Cloud"},
        {"name_list": ["Aliyun"], "type": "Aliyun Cloud"},
        {"name_list": ["JVM", "SNMP Trap"], "type": "Other"},
    ]


def default_order_name_matches(obj_name, catalog_name):
    """大小写不敏感匹配对象名与 DEFAULT_OBJ_ORDER 目录名。"""
    if not isinstance(obj_name, str) or not isinstance(catalog_name, str):
        return False
    return obj_name.casefold() == catalog_name.casefold()


def resolve_default_object_order(obj_name, type_id, catalog=None):
    """按 DEFAULT_OBJ_ORDER 计算应赋 order；未命中返回 None。"""
    items = catalog if catalog is not None else MonitorObjConstants.DEFAULT_OBJ_ORDER
    for item in items:
        if item.get("type") != type_id:
            continue
        for name_idx, name in enumerate(item.get("name_list", [])):
            if default_order_name_matches(obj_name, name):
                return name_idx
    return None


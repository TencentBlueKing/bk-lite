from apps.node_mgmt.constants.node import NodeConstants


class CollectorConstants:
    """采集器相关常量"""

    # 采集器下发目录
    DOWNLOAD_DIR = {
        NodeConstants.LINUX_OS: "/opt/fusion-collectors/bin",
        NodeConstants.WINDOWS_OS: "C:\\gse\\fusion-collectors\\bin",
    }

    TAG_ENUM = {
        "monitor": {"is_app": True, "name": "Monitor"},
        "log": {"is_app": True, "name": "Log"},
        "cmdb": {"is_app": True, "name": "CMDB"},

        "linux": {"is_app": False, "name": "Linux"},
        "windows": {"is_app": False, "name": "Windows"},

        "jmx": {"is_app": False, "name": "JMX"},
        "exporter": {"is_app": False, "name": "Exporter"},
        "beat": {"is_app": False, "name": "Beat"},
    }

    # 容器节点才会默认初始化的采集器配置
    DEFAULT_CONTAINER_COLLECTOR_CONFIGS = ["Snmptrapd"]

    IGNORE_ERROR_COLLECTORS = ["Metricbeat", "Auditbeat", "Filebeat", "Packetbeat"]
    IGNORE_ERROR_COLLECTORS_MESSAGES = [
        "Exiting: one or more modules must be configured\n",
        "Exiting: no modules or inputs enabled and configuration reloading disabled. What files do you want me to watch?\n"
    ]

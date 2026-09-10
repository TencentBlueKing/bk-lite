from apps.node_mgmt.constants.node import NodeConstants


class CollectorConstants:
    """采集器相关常量"""

    # 采集器下发目录
    DOWNLOAD_DIR = {
        NodeConstants.LINUX_OS: "/opt/fusion-collectors/bin",
        NodeConstants.WINDOWS_OS: "C:\\fusion-collectors\\bin",
    }

    TAG_ENUM = {
        "monitor": {"is_app": True, "name": "Monitor"},
        "log": {"is_app": True, "name": "Log"},
        "cmdb": {"is_app": True, "name": "CMDB"},
        "apm": {"is_app": True, "name": "APM"},
        "executor": {"is_app": True, "name": "Executor"},
        "linux": {"is_app": False, "name": "Linux"},
        "windows": {"is_app": False, "name": "Windows"},
        "jmx": {"is_app": False, "name": "JMX"},
        "exporter": {"is_app": False, "name": "Exporter"},
        "beat": {"is_app": False, "name": "Beat"},
    }

    # 容器节点才会默认初始化的采集器配置
    DEFAULT_CONTAINER_COLLECTOR_CONFIGS = ["Snmptrapd", "Ansible-Executor", "OTel-Collector"]

    IGNORE_ERROR_COLLECTORS = ["Metricbeat", "Auditbeat", "Filebeat", "Packetbeat", "Winlogbeat"]
    IGNORE_ERROR_COLLECTORS_MESSAGES = [
        "one or more modules must be configured",
        "no modules or inputs enabled and configuration reloading disabled. What files do you want me to watch?",
        "at least one event log must be configured as part of event_logs",
        "Unable to start collector after 3 tries, giving up!",
    ]

    # 控制机只保留 Sidecar。NATS-Executor / Ansible-Executor 作为托管组件暴露。
    IGNORE_COLLECTORS = []

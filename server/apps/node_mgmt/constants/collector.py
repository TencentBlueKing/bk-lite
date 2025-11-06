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

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

    # 需要对密码进行URL编码的采集器ID集合
    # 这些采集器的密码会在URL中使用，因此需要进行URL编码以确保特殊字符正确传递
    URL_ENCODE_PASSWORD_COLLECTORS = {"telegraf_linux", "telegraf_windows"}

from apps.node_mgmt.constants.node import NodeConstants


class CollectorConstants:
    """采集器相关常量"""

    # 采集器下发目录
    DOWNLOAD_DIR = {
        NodeConstants.LINUX_OS: "/opt/fusion-collectors/bin",
        NodeConstants.WINDOWS_OS: "C:\\gse\\fusion-collectors\\bin",
    }

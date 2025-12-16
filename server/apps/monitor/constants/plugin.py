class PluginConstants:
    """插件相关常量"""

    # 插件目录
    DIRECTORY = "apps/monitor/support-files/plugins"

    # 插件状态有正常和失联两种，后续可以根据需要扩展，默认用失联
    STATUS_NORMAL = "normal"
    STATUS_OFFLINE = "offline"
    STATUS_ENUM = {
        STATUS_NORMAL: "正常",
        STATUS_OFFLINE: "失联",
    }

    # 采集方式有自动和手动两种
    COLLECT_MODE_AUTO = "auto"
    COLLECT_MODE_MANUAL = "manual"
    COLLECT_MODE_ENUM = {
        COLLECT_MODE_AUTO: "自动",
        COLLECT_MODE_MANUAL: "手动",
    }
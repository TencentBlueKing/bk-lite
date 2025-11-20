class CloudRegionServiceConstants:
    # 服务名称
    STARGAZER_SERVICE_NAME = "stargazer"
    NATS_EXECUTOR_SERVICE_NAME = "nats-executor"
    SERVICES = [STARGAZER_SERVICE_NAME, NATS_EXECUTOR_SERVICE_NAME]

    # 节点状态枚举
    NORMAL = "normal"  # 正常
    UNINSTALLED = "uninstall"  # 未安装
    ERROR = "error"  # 异常
    STATUS_ENUM = {
        NORMAL: "正常",
        UNINSTALLED: "未安装",
        ERROR: "异常",
    }

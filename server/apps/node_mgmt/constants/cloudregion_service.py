class CloudRegionServiceConstants:
    # 服务名称
    STARGAZER_SERVICE_NAME = "stargazer"
    NATS_EXECUTOR_SERVICE_NAME = "nats-executor"
    SERVICES = [STARGAZER_SERVICE_NAME, NATS_EXECUTOR_SERVICE_NAME]

    # 节点状态枚举
    NORMAL = "normal"  # 正常
    NOT_DEPLOYED = "not_deployed"  # 未部署
    ERROR = "error"  # 异常
    STATUS_ENUM = {
        NORMAL: "正常",
        NOT_DEPLOYED: "未部署",
        ERROR: "异常",
    }

    # 部署状态枚举
    NOT_DEPLOYED_STATUS = 0  # 未部署
    DEPLOYING = 1  # 部署中
    DEPLOYED = 2  #  已部署
    ERROR = 3  # 部署失败
    DEPLOY_STATUS_ENUM = {
        DEPLOYED: "未部署",
        NOT_DEPLOYED_STATUS: "部署中",
        DEPLOYING: "已部署",
        ERROR: "部署失败",
    }

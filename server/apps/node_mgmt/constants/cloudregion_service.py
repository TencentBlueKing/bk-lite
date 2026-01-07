class CloudRegionServiceConstants:
    # 服务名称
    STARGAZER_SERVICE_NAME = "stargazer"
    NATS_EXECUTOR_SERVICE_NAME = "nats-executor"
    SERVICES = [STARGAZER_SERVICE_NAME, NATS_EXECUTOR_SERVICE_NAME]

    # 节点状态枚举
    NORMAL = "normal"  # 正常
    NOT_DEPLOYED = "not_deployed"  # 未部署
    N_ERROR = "error"  # 异常
    STATUS_ENUM = {
        NORMAL: "正常",
        NOT_DEPLOYED: "未部署",
        N_ERROR: "异常",
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

    LOCAL_CA_CERT_PATH = "/etc/nats/certs/ca.crt"
    REMOTE_CA_CERT_PATH = "/opt/bk-lite/conf/certs"

    FUSION_COLLECTOR_SERVICE_NAME = "fusion-collector"

    # 服务安装命令
    SERVICE_INSTALL_COMMANDS = {
        NATS_EXECUTOR_SERVICE_NAME: """docker run -d \
  --name nats-executor \
  --network=host \
  --restart always \
  -e NATS_INSTANCE_ID={cloud_region_id} \
  -e NATS_URLS="tls://{NATS_ADMIN_USERNAME}:{NATS_ADMIN_PASSWORD}@nats:4222" \
  -e NATS_CA_FILE=/etc/nats/certs/ca.crt \
  -v /opt/bk-lite/conf/certs:/etc/nats/certs:ro \
  "{DOCKER_IMAGE_NATS_EXECUTOR}" """,
        STARGAZER_SERVICE_NAME: """docker run -d \
  --name stargazer \
  --network prod \
  -e NATS_URLS="tls://{NATS_ADMIN_USERNAME}:{NATS_ADMIN_PASSWORD}@nats:4222" \
  -e UV_OFFLINE=True \
  -e NATS_TLS_ENABLED=true \
  -e NATS_TLS_CA_FILE=/etc/certs/ca.crt \
  -v /opt/bk-lite/conf/certs:/etc/certs:ro \
  "{DOCKER_IMAGE_STARGAZER}" """,
        FUSION_COLLECTOR_SERVICE_NAME: """"""
    }
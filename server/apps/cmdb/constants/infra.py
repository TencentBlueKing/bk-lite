class InfraConstants:
    """CMDB 基础设施配置相关常量"""

    REQUEST_TIMEOUT = 30

    TOKEN_EXPIRE_TIME = 60 * 30

    TOKEN_MAX_USAGE = 5

    COLLECTOR_CLUSTER_ID_PATTERN = r"^[A-Za-z0-9_-]+$"

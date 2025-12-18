class InfraConstants:
    """基础设施配置相关常量"""

    # HTTP 请求超时设置（秒）
    REQUEST_TIMEOUT = 30

    # 安装令牌过期时间（秒）- 30分钟
    TOKEN_EXPIRE_TIME = 60 * 30

    # 安装令牌最大使用次数
    TOKEN_MAX_USAGE = 5

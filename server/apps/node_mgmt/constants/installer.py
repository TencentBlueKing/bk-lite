class InstallerConstants:
    """安装器相关常量"""

    # HTTP 请求超时设置（秒）
    REQUEST_TIMEOUT = 30

    # 安装令牌过期时间（秒）- 30分钟
    INSTALL_TOKEN_EXPIRE_TIME = 60 * 30

    # 安装令牌最大使用次数
    INSTALL_TOKEN_MAX_USAGE = 5

    # 下载令牌过期时间（秒）- 10分钟
    DOWNLOAD_TOKEN_EXPIRE_TIME = 60 * 10

    # 下载令牌最大使用次数
    DOWNLOAD_TOKEN_MAX_USAGE = 3

    # 安装令牌缓存键前缀
    INSTALL_TOKEN_CACHE_PREFIX = "node_install_token"

    # 下载令牌缓存键前缀
    DOWNLOAD_TOKEN_CACHE_PREFIX = "package_download_token"


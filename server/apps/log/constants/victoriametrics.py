import os


class VictoriaLogsConstants:
    """VictoriaLogs服务相关常量"""

    # VictoriaLogs服务信息
    HOST = os.getenv("VICTORIALOGS_HOST")
    USER = os.getenv("VICTORIALOGS_USER")
    PWD = os.getenv("VICTORIALOGS_PWD")

    # SSL验证配置，支持环境变量控制
    SSL_VERIFY = os.getenv("VICTORIALOGS_SSL_VERIFY", "false").lower() == "true"

    # SSE连接配置
    MAX_CONNECTION_TIME = int(os.getenv("SSE_MAX_CONNECTION_TIME", "1800"))  # 默认30分钟
    KEEPALIVE_INTERVAL = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "45"))     # 默认45秒
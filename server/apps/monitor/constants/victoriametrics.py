import os


class VictoriaMetricsConstants:
    """VictoriaMetrics服务相关常量"""

    # VictoriaMetrics服务信息
    HOST = os.getenv("VICTORIAMETRICS_HOST")
    USER = os.getenv("VICTORIAMETRICS_USER")
    PWD = os.getenv("VICTORIAMETRICS_PWD")

    # SSL验证配置，支持环境变量控制
    SSL_VERIFY = os.getenv("VICTORIAMETRICS_SSL_VERIFY", "false").lower() == "true"


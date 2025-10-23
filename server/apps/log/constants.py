# victoriametrics服务信息
import os

VICTORIALOGS_HOST = os.getenv("VICTORIALOGS_HOST")
VICTORIALOGS_USER = os.getenv("VICTORIALOGS_USER")
VICTORIALOGS_PWD = os.getenv("VICTORIALOGS_PWD")
# 添加SSL验证配置，支持环境变量控制
VICTORIALOGS_SSL_VERIFY = os.getenv("VICTORIALOGS_SSL_VERIFY", "false").lower() == "true"

# SSE连接配置
SSE_MAX_CONNECTION_TIME = int(os.getenv("SSE_MAX_CONNECTION_TIME", "1800"))  # 默认30分钟
SSE_KEEPALIVE_INTERVAL = int(os.getenv("SSE_KEEPALIVE_INTERVAL", "45"))     # 默认45秒

# 策略相关常量
POLICY_MODULE = "policy"

# 采集实例相关常量
INSTANCE_MODULE = "instance"

# 日志分组相关常量
LOG_GROUP_MODULE = "log_group"
DEFAULT_PERMISSION = ['View', 'Operate']

# 告警状态
ALERT_STATUS_NEW = "new"
ALERT_STATUS_CLOSED = "closed"
ALERT_STATUS_CHOICES = [
    (ALERT_STATUS_NEW, "活跃"),
    (ALERT_STATUS_CLOSED, "关闭"),
]

# 告警类型
KEYWORD = "keyword"
AGGREGATE = "aggregate"
ALERT_TYPE = [KEYWORD, AGGREGATE]

# 告警级别
ALERT_LEVEL_INFO = "info"
ALERT_LEVEL_WARNING = "warning"
ALERT_LEVEL_ERROR = "error"
ALERT_LEVEL_CRITICAL = "critical"

# 通知类型
NOTICE_TYPE_EMAIL = "email"
NOTICE_TYPE_SMS = "sms"
NOTICE_TYPE_WEBHOOK = "webhook"

# WEB URL
WEB_URL = os.getenv("WEB_URL", "http://localhost:8000")

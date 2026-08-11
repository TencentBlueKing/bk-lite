import logging
import os
import sys

from config.components.base import APP_CODE, BASE_DIR, DEBUG

if DEBUG:
    log_dir = os.path.join(os.path.dirname(BASE_DIR), "logs", APP_CODE)
else:
    LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs/")
    log_dir = os.path.join(os.path.join(LOG_DIR, APP_CODE))

if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 根据 DEBUG 环境变量设置日志级别
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

# 仅用于历史日志分组规则的迁移窗口。默认空集合保持 fail-closed；上线前通过
# audit_log_group_rule_modes 盘点并只加入已明确需要短期保留旧 OR 语义的分组 ID。
LOG_GROUP_LEGACY_OR_GROUP_IDS = frozenset(
    item.strip() for item in os.getenv("LOG_GROUP_LEGACY_OR_GROUP_IDS", "").split(",") if item.strip()
)
LOG_GROUP_RULE_MODE_ENFORCEMENT = os.getenv("LOG_GROUP_RULE_MODE_ENFORCEMENT", "strict").strip().lower()
if LOG_GROUP_RULE_MODE_ENFORCEMENT not in {"legacy", "strict"}:
    raise ValueError("LOG_GROUP_RULE_MODE_ENFORCEMENT must be legacy or strict")


class SafeConsoleHandler(logging.StreamHandler):
    """Windows GBK 控制台写 UTF-8 日志时避免 UnicodeEncodeError 中断 emit。"""

    def __init__(self, stream=None):
        super().__init__(stream or sys.stderr)

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                encoding = getattr(stream, "encoding", None) or "utf-8"
                safe = msg.encode(encoding, errors="replace").decode(encoding, errors="replace")
                stream.write(safe + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class IgnoreSpecificPaths(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        try:
            path = msg.split(" ")[1]
        except IndexError:
            return True

        # 前缀匹配
        exclude_prefixes = [
            "/node_mgmt/open_api/node",
        ]
        # 后缀匹配
        exclude_suffixes = []
        # 静态路径
        exclude_paths = []

        if any(path.startswith(prefix) for prefix in exclude_prefixes):
            return False
        if any(path.endswith(suffix) for suffix in exclude_suffixes):
            return False
        if path in exclude_paths:
            return False
        return True


class SuppressSuccessfulSidecarAccessLogs(logging.Filter):
    """过滤 Uvicorn 中高频的 Sidecar 成功访问日志，异常状态仍保留。"""

    SIDECAR_OPEN_API_PATH_PREFIXES = (
        "/node_mgmt/open_api/node",
        "/api/v1/node_mgmt/open_api/node",
    )

    def filter(self, record):
        # Uvicorn access log 参数依次为 client、method、path、HTTP version、status。
        if not isinstance(record.args, tuple) or len(record.args) < 5:
            return True

        path = str(record.args[2])
        try:
            status_code = int(record.args[4])
        except (TypeError, ValueError):
            return True

        is_sidecar_request = any(path.startswith(prefix) for prefix in self.SIDECAR_OPEN_API_PATH_PREFIXES)
        return not (is_sidecar_request and status_code < 400)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ignore_paths": {
            "()": IgnoreSpecificPaths,
        },
        "suppress_successful_sidecar_access_logs": {
            "()": SuppressSuccessfulSidecarAccessLogs,
        },
    },
    "formatters": {
        "simple": {
            "format": "%(levelname)s [%(asctime)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "verbose": {
            "format": "%(levelname)s [%(asctime)s] %(pathname)s " "%(lineno)d %(funcName)s %(process)d %(thread)d " "\n \t %(message)s \n",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "()": SafeConsoleHandler,
            "formatter": "simple",
            "filters": ["ignore_paths"],  # 添加 filter
        },
        "uvicorn_access_console": {
            "level": "INFO",
            "()": SafeConsoleHandler,
            "formatter": "simple",
            "filters": ["suppress_successful_sidecar_access_logs"],
        },
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
        "root": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "%s.log" % APP_CODE),
            "encoding": "utf-8",
        },
        "db": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "db.log"),
            "encoding": "utf-8",
        },
        "alert": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "alert.log"),
            "maxBytes": 100 * 1024 * 1024,  # 添加文件大小限制
            "backupCount": 5,  # 添加备份文件数量
            "encoding": "utf-8",  # 添加编码格式
        },
        "cmdb": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "cmdb.log"),
            "encoding": "utf-8",
        },
        "operation_analysis": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "operation_analysis.log"),
            "encoding": "utf-8",
        },
        "nats": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "nats.log"),
            "encoding": "utf-8",
        },
        "monitor": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "monitor.log"),
            "encoding": "utf-8",
        },
        "node": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "node.log"),
            "encoding": "utf-8",
        },
        "ops-console": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "ops-console.log"),
            "encoding": "utf-8",
        },
        "system-manager": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "system-manager.log"),
            "encoding": "utf-8",
        },
        "opspilot": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "opspilot.log"),
            "encoding": "utf-8",
        },
        "job": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "job.log"),
            "encoding": "utf-8",
        },
        "playground": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "playground.log"),
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {"handlers": ["null"], "level": "INFO", "propagate": True},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": True},
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.db.backends": {"handlers": ["db"], "level": "INFO", "propagate": True},
        "app": {"handlers": ["root", "console"], "level": LOG_LEVEL, "propagate": True},
        "cmdb": {"handlers": ["cmdb", "console"], "level": LOG_LEVEL, "propagate": True},
        "operation_analysis": {"handlers": ["operation_analysis", "console"], "level": LOG_LEVEL, "propagate": True},
        "nats": {"handlers": ["nats", "console"], "level": LOG_LEVEL, "propagate": True},
        "monitor": {"handlers": ["monitor", "console"], "level": LOG_LEVEL, "propagate": True},
        "node": {"handlers": ["node", "console"], "level": LOG_LEVEL, "propagate": True},
        "ops-console": {"handlers": ["ops-console", "console"], "level": LOG_LEVEL, "propagate": True},
        "system-manager": {"handlers": ["system-manager", "console"], "level": LOG_LEVEL, "propagate": True},
        "opspilot": {"handlers": ["opspilot", "console"], "level": LOG_LEVEL, "propagate": True},
        "job": {"handlers": ["job", "console"], "level": LOG_LEVEL, "propagate": True},
        "alert": {"handlers": ["alert", "console"], "level": LOG_LEVEL, "propagate": True},
        "celery": {"handlers": ["root"], "level": "INFO", "propagate": True},
        "playground": {"handlers": ["playground", "console"], "level": LOG_LEVEL, "propagate": True},
        "uvicorn.access": {
            "handlers": ["uvicorn_access_console"],
            "level": "INFO",
            "propagate": False,
        },
        # httpx 会在 INFO 级别输出每次成功请求:
        # HTTP Request: POST ... "HTTP/1.1 200 OK"。解析/构建调用 LLM 时会刷屏,
        # 这里仅保留 warning/error，异常仍可见。
        "httpx": {"handlers": ["root", "console"], "level": "WARNING", "propagate": False},
        "httpcore": {"handlers": ["root", "console"], "level": "WARNING", "propagate": False},
        "openai": {"handlers": ["root", "console"], "level": "WARNING", "propagate": False},
    },
}

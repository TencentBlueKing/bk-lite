import os
import logging
from config.components.base import APP_CODE, BASE_DIR, DEBUG

if DEBUG:
    log_dir = os.path.join(os.path.dirname(BASE_DIR), "logs", APP_CODE)
else:
    LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs/")
    log_dir = os.path.join(os.path.join(LOG_DIR, APP_CODE))

if not os.path.exists(log_dir):
    os.makedirs(log_dir)


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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
            "ignore_paths": {
                "()": IgnoreSpecificPaths,
            },
        },
    "formatters": {
        "simple": {
            "format": "%(levelname)s [%(asctime)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "verbose": {
            "format": "%(levelname)s [%(asctime)s] %(pathname)s "
            "%(lineno)d %(funcName)s %(process)d %(thread)d "
            "\n \t %(message)s \n",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["ignore_paths"],  # 添加 filter
        },
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
        "root": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "%s.log" % APP_CODE),
        },
        "db": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "db.log"),
        },
        "alert": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "alert.log"),
            "maxBytes": 100 * 1024 * 1024,  # 添加文件大小限制
            "backupCount": 5,               # 添加备份文件数量
            "encoding": "utf-8",            # 添加编码格式
        },
        "cmdb": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "cmdb.log"),
        },
        "operation_analysis": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "operation_analysis.log"),
        },
        "nats": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "nats.log"),
        },
        "monitor": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "monitor.log"),
        },
        "node": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "node.log"),
        },
        "ops-console": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "ops-console.log"),
        },
        "system-manager": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "system-manager.log"),
        },
        "opspilot": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "opspilot.log"),
        },
        "playground": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "verbose",
            "filename": os.path.join(log_dir, "playground.log"),
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
        "app": {"handlers": ["root", "console"], "level": "DEBUG", "propagate": True},
        "cmdb": {"handlers": ["cmdb", "console"], "level": "DEBUG", "propagate": True},
        "operation_analysis": {"handlers": ["operation_analysis", "console"], "level": "DEBUG", "propagate": True},
        "nats": {"handlers": ["nats", "console"], "level": "DEBUG", "propagate": True},
        "monitor": {"handlers": ["monitor", "console"], "level": "DEBUG", "propagate": True},
        "node": {"handlers": ["node", "console"], "level": "DEBUG", "propagate": True},
        "ops-console": {"handlers": ["ops-console", "console"], "level": "DEBUG", "propagate": True},
        "system-manager": {"handlers": ["system-manager", "console"], "level": "DEBUG", "propagate": True},
        "opspilot": {"handlers": ["opspilot", "console"], "level": "DEBUG", "propagate": True},
        "alert": {"handlers": ["alert", "console"], "level": "DEBUG", "propagate": True},
        "celery": {"handlers": ["root"], "level": "INFO", "propagate": True},
        "playground": {"handlers": ["playground", "console"], "level": "DEBUG", "propagate": True},
    },
}

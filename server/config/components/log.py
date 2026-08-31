import logging
import os
import sys

from config.components.base import APP_CODE, BASE_DIR, DEBUG

if DEBUG:
    log_dir = os.path.join(os.path.dirname(BASE_DIR), "logs", APP_CODE)
else:
    LOG_DIR = os.getenv("LOG_DIR", "/tmp/logs/")
    log_dir = os.path.join(os.path.join(LOG_DIR, APP_CODE))

DEFAULT_LOG_FILE_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_LOG_FILE_BACKUP_COUNT = 5
DEFAULT_LOG_LEVEL = "INFO"
ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def parse_positive_int(raw, default, *, name):
    if raw is None or str(raw).strip() == "":
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def parse_bool(raw, default, *, name):
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be a boolean")


def parse_log_level(raw, default=DEFAULT_LOG_LEVEL):
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip().upper()
    if value == "WARN":
        value = "WARNING"
    if value not in ALLOWED_LOG_LEVELS:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    return value


LOG_FILE_OUTPUT = parse_bool(os.getenv("LOG_FILE_OUTPUT"), False, name="LOG_FILE_OUTPUT")
LOG_LEVEL = parse_log_level(os.getenv("LOG_LEVEL"))
LOG_FILE_MAX_BYTES = parse_positive_int(
    os.getenv("LOG_FILE_MAX_BYTES"),
    DEFAULT_LOG_FILE_MAX_BYTES,
    name="LOG_FILE_MAX_BYTES",
)
LOG_FILE_BACKUP_COUNT = parse_positive_int(
    os.getenv("LOG_FILE_BACKUP_COUNT"),
    DEFAULT_LOG_FILE_BACKUP_COUNT,
    name="LOG_FILE_BACKUP_COUNT",
)


def rotating_file_handler(filename, **overrides):
    config = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "verbose",
        "filename": os.path.join(log_dir, filename),
        "maxBytes": LOG_FILE_MAX_BYTES,
        "backupCount": LOG_FILE_BACKUP_COUNT,
        "encoding": "utf-8",
    }
    config.update(overrides)
    if config["maxBytes"] <= 0:
        raise ValueError("rotating file handler maxBytes must be positive")
    if config["backupCount"] <= 0:
        raise ValueError("rotating file handler backupCount must be positive")
    return config

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


FILE_HANDLER_FILES = {
    "root": "%s.log" % APP_CODE,
    "db": "db.log",
    "alert": "alert.log",
    "cmdb": "cmdb.log",
    "operation_analysis": "operation_analysis.log",
    "nats": "nats.log",
    "monitor": "monitor.log",
    "log": "log.log",
    "apm": "apm.log",
    "node": "node.log",
    "ops-console": "ops-console.log",
    "system-manager": "system-manager.log",
    "opspilot": "opspilot.log",
    "job": "job.log",
    "playground": "playground.log",
}

APP_LOGGER_FILE_HANDLERS = {
    "app": "root",
    "cmdb": "cmdb",
    "operation_analysis": "operation_analysis",
    "nats": "nats",
    "monitor": "monitor",
    "log": "log",
    "apm": "apm",
    "node": "node",
    "ops-console": "ops-console",
    "system-manager": "system-manager",
    "opspilot": "opspilot",
    "job": "job",
    "alert": "alert",
    "playground": "playground",
}


def _app_handlers(file_handler_name, *, log_file_output):
    if log_file_output:
        return [file_handler_name, "console"]
    return ["console"]


def build_logging_config(*, log_level=None, log_file_output=None):
    log_level = LOG_LEVEL if log_level is None else log_level
    log_file_output = LOG_FILE_OUTPUT if log_file_output is None else log_file_output

    handlers = {
        "console": {
            "level": "DEBUG",
            "()": SafeConsoleHandler,
            "formatter": "simple",
            "filters": ["ignore_paths"],
        },
        "uvicorn_access_console": {
            "level": "INFO",
            "()": SafeConsoleHandler,
            "formatter": "simple",
            "filters": ["suppress_successful_sidecar_access_logs"],
        },
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
    }
    if log_file_output:
        os.makedirs(log_dir, exist_ok=True)
        for name, filename in FILE_HANDLER_FILES.items():
            handlers[name] = rotating_file_handler(filename)

    http_client_handlers = ["root", "console"] if log_file_output else ["console"]
    loggers = {
        "django": {"handlers": ["null"], "level": "INFO", "propagate": True},
        "django.server": {"handlers": ["console"], "level": "INFO", "propagate": True},
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.db.backends": {
            "handlers": ["db"] if log_file_output else ["null"],
            "level": "INFO",
            "propagate": True,
        },
        "celery": {
            "handlers": ["root"] if log_file_output else ["console"],
            "level": log_level,
            "propagate": True,
        },
        "uvicorn.access": {
            "handlers": ["uvicorn_access_console"],
            "level": "INFO",
            "propagate": False,
        },
        # httpx 会在 INFO 级别输出每次成功请求:
        # HTTP Request: POST ... "HTTP/1.1 200 OK"。解析/构建调用 LLM 时会刷屏,
        # 这里仅保留 warning/error，异常仍可见。
        "httpx": {"handlers": http_client_handlers, "level": "WARNING", "propagate": False},
        "httpcore": {"handlers": http_client_handlers, "level": "WARNING", "propagate": False},
        "openai": {"handlers": http_client_handlers, "level": "WARNING", "propagate": False},
    }
    for logger_name, file_handler_name in APP_LOGGER_FILE_HANDLERS.items():
        loggers[logger_name] = {
            "handlers": _app_handlers(file_handler_name, log_file_output=log_file_output),
            "level": log_level,
            "propagate": True,
        }

    return {
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
        "handlers": handlers,
        "loggers": loggers,
    }


LOGGING = build_logging_config()

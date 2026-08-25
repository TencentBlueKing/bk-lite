"""网络设备 SNMP 采集的独立滚动文件日志。"""

from __future__ import annotations

import contextvars
import logging
import os
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterator

from sanic.log import logger as sanic_logger

_SNMP_LOG_SCOPE = contextvars.ContextVar("stargazer_snmp_log_scope", default=False)
_HANDLER_PATH_ATTRIBUTE = "_stargazer_snmp_log_path"


class _SnmpCollectionFilter(logging.Filter):
    _MESSAGE_MARKERS = (
        "plugin_name=snmp_facts",
        "plugin_ref=network.config",
        "插件=snmp_facts",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        if _SNMP_LOG_SCOPE.get():
            return True
        message = record.getMessage()
        return any(marker in message for marker in self._MESSAGE_MARKERS)


@contextmanager
def snmp_log_scope(enabled: bool) -> Iterator[None]:
    """让 SNMP 插件内部未携带结构化字段的日志也进入独立文件。"""

    if not enabled:
        yield
        return
    token = _SNMP_LOG_SCOPE.set(True)
    try:
        yield
    finally:
        _SNMP_LOG_SCOPE.reset(token)


def configure_snmp_file_logging(
    *,
    log_path: str | Path | None = None,
    target_logger: logging.Logger | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> RotatingFileHandler | None:
    """安装 SNMP 文件 handler；失败不阻断 Stargazer 启动。"""

    destination = Path(log_path or os.getenv("SNMP_LOG_FILE", "logs/snmp_facts.log")).expanduser()
    logger = target_logger or sanic_logger
    normalized_path = str(destination.resolve())
    for existing in logger.handlers:
        if getattr(existing, _HANDLER_PATH_ATTRIBUTE, None) == normalized_path:
            return existing

    try:
        resolved_max_bytes = max_bytes or int(os.getenv("SNMP_LOG_MAX_BYTES", str(50 * 1024 * 1024)))
        resolved_backup_count = backup_count if backup_count is not None else int(os.getenv("SNMP_LOG_BACKUP_COUNT", "5"))
        destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            destination,
            maxBytes=resolved_max_bytes,
            backupCount=resolved_backup_count,
            encoding="utf-8",
        )
        setattr(handler, _HANDLER_PATH_ATTRIBUTE, normalized_path)
        handler.addFilter(_SnmpCollectionFilter())
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        try:
            destination.chmod(0o640)
        except OSError:
            pass
        logger.info(
            "event=snmp_file_log_ready path=%s max_bytes=%s backup_count=%s",
            destination,
            resolved_max_bytes,
            resolved_backup_count,
        )
        return handler
    except (OSError, ValueError) as error:
        logger.warning(
            "event=snmp_file_log_unavailable path=%s error_type=%s",
            destination,
            type(error).__name__,
        )
        return None

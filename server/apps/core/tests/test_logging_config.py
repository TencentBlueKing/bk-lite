import io
import logging
from pathlib import Path

import pytest
from logging.handlers import RotatingFileHandler

from config.components.log import (
    DEFAULT_LOG_FILE_BACKUP_COUNT,
    DEFAULT_LOG_FILE_MAX_BYTES,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    LOGGING,
    SafeConsoleHandler,
    parse_positive_int,
    rotating_file_handler,
)

SERVER_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_APP_FILE_LOGGERS = ("monitor", "log", "apm", "node", "alert")


def test_deployment_env_templates_disable_debug_by_default():
    templates = (
        "envs/.env.example",
        "support-files/env/.env.opspilot.example",
        "support-files/env/.env.system_mgmt.example",
    )

    for relative_path in templates:
        content = (SERVER_ROOT / relative_path).read_text(encoding="utf-8")
        assert "DEBUG=False" in content.splitlines(), f"{relative_path} must default to INFO logging"


def test_http_client_success_logs_are_suppressed_but_warnings_remain():
    for logger_name in ("httpx", "httpcore", "openai"):
        logger_config = LOGGING["loggers"].get(logger_name)
        assert logger_config is not None
        assert logger_config["level"] == "WARNING"
        assert logger_config["propagate"] is False

        logger = logging.getLogger(logger_name)
        logger.setLevel(logger_config["level"])
        assert not logger.isEnabledFor(logging.INFO)
        assert logger.isEnabledFor(logging.WARNING)


def test_console_handler_uses_safe_stream_and_file_handlers_are_utf8():
    assert LOGGING["handlers"]["console"]["()"] is SafeConsoleHandler
    for name, handler in LOGGING["handlers"].items():
        if handler.get("class") == "logging.handlers.RotatingFileHandler":
            assert handler.get("encoding") == "utf-8", name


def _rotating_file_handlers():
    return {
        name: handler
        for name, handler in LOGGING["handlers"].items()
        if handler.get("class") == "logging.handlers.RotatingFileHandler"
    }


def test_parse_positive_int_uses_default_and_rejects_disabled_rotation():
    assert parse_positive_int(None, 100, name="LOG_FILE_MAX_BYTES") == 100
    assert parse_positive_int(" 2048 ", 100, name="LOG_FILE_MAX_BYTES") == 2048
    with pytest.raises(ValueError, match="LOG_FILE_MAX_BYTES"):
        parse_positive_int("0", 100, name="LOG_FILE_MAX_BYTES")
    with pytest.raises(ValueError, match="LOG_FILE_BACKUP_COUNT"):
        parse_positive_int("-1", 5, name="LOG_FILE_BACKUP_COUNT")


def test_rotating_file_handler_applies_defaults_and_rejects_zero_limits():
    config = rotating_file_handler("demo.log")
    assert config["class"] == "logging.handlers.RotatingFileHandler"
    assert config["maxBytes"] == LOG_FILE_MAX_BYTES == DEFAULT_LOG_FILE_MAX_BYTES
    assert config["backupCount"] == LOG_FILE_BACKUP_COUNT == DEFAULT_LOG_FILE_BACKUP_COUNT
    assert config["encoding"] == "utf-8"
    assert config["filename"].endswith("demo.log")

    overridden = rotating_file_handler("demo.log", maxBytes=2 * 1024 * 1024, backupCount=3)
    assert overridden["maxBytes"] == 2 * 1024 * 1024
    assert overridden["backupCount"] == 3

    with pytest.raises(ValueError, match="maxBytes"):
        rotating_file_handler("demo.log", maxBytes=0)
    with pytest.raises(ValueError, match="backupCount"):
        rotating_file_handler("demo.log", backupCount=0)


def test_all_rotating_file_handlers_share_default_rotation_limits():
    rotating = _rotating_file_handlers()
    assert rotating
    for name, handler in rotating.items():
        assert handler["maxBytes"] == LOG_FILE_MAX_BYTES, name
        assert handler["backupCount"] == LOG_FILE_BACKUP_COUNT, name
        assert handler["maxBytes"] > 0, name
        assert handler["backupCount"] > 0, name


def test_product_app_loggers_keep_info_on_dedicated_rotating_files():
    for name in PRODUCT_APP_FILE_LOGGERS:
        handler = LOGGING["handlers"][name]
        logger_config = LOGGING["loggers"][name]
        assert handler["class"] == "logging.handlers.RotatingFileHandler"
        assert handler["maxBytes"] > 0
        assert name in logger_config["handlers"]
        assert logger_config["level"] in {"INFO", "DEBUG"}


def test_configured_node_handler_rolls_over_when_file_exceeds_max_bytes(tmp_path):
    cfg = LOGGING["handlers"]["node"]
    assert cfg["class"] == "logging.handlers.RotatingFileHandler"
    assert cfg["maxBytes"] > 0
    path = tmp_path / "node.log"
    max_bytes = 64
    path.write_bytes(b"x" * (max_bytes + 1))
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=cfg["backupCount"],
        encoding="utf-8",
    )
    try:
        record = logging.LogRecord("node", logging.INFO, __file__, 1, "overflow", (), None)
        assert handler.shouldRollover(record)
    finally:
        handler.close()


def test_runtime_product_loggers_enable_info_and_attach_rotating_files():
    for name in PRODUCT_APP_FILE_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.isEnabledFor(logging.INFO), name
        rotating = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]
        assert rotating, name
        assert rotating[0].maxBytes > 0, name
        assert rotating[0].backupCount > 0, name


def test_safe_console_handler_replaces_unencodable_chars_on_gbk_stream():
    class GbkStream(io.TextIOBase):
        encoding = "gbk"

        def __init__(self):
            self.chunks = []

        def write(self, s):
            # 模拟 Windows GBK 控制台:遇到 © 会抛 UnicodeEncodeError
            s.encode("gbk")
            self.chunks.append(s)
            return len(s)

        def flush(self):
            return None

    stream = GbkStream()
    handler = SafeConsoleHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord("opspilot", logging.INFO, __file__, 1, "copyright \xa9 ok", (), None)
    handler.emit(record)
    assert stream.chunks
    assert "ok" in stream.chunks[0]
    assert "\xa9" not in stream.chunks[0]

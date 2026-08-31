import io
import logging
from pathlib import Path

import pytest
from logging.handlers import RotatingFileHandler

from config.components.log import (
    DEFAULT_LOG_FILE_BACKUP_COUNT,
    DEFAULT_LOG_FILE_MAX_BYTES,
    DEFAULT_LOG_LEVEL,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    LOGGING,
    SafeConsoleHandler,
    build_logging_config,
    parse_bool,
    parse_log_level,
    parse_positive_int,
    rotating_file_handler,
)

SERVER_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_APP_FILE_LOGGERS = ("monitor", "log", "apm", "node", "alert")


def test_deployment_env_templates_disable_debug_and_default_container_logging():
    templates = (
        "envs/.env.example",
        "support-files/env/.env.opspilot.example",
        "support-files/env/.env.system_mgmt.example",
    )

    for relative_path in templates:
        lines = (SERVER_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
        assert "DEBUG=False" in lines, f"{relative_path} must default Django DEBUG off"
        assert "LOG_LEVEL=INFO" in lines, f"{relative_path} must default LOG_LEVEL to INFO"
        assert "LOG_FILE_OUTPUT=false" in lines, f"{relative_path} must default file logging off"


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


def _rotating_file_handlers(config=None):
    config = LOGGING if config is None else config
    return {
        name: handler
        for name, handler in config["handlers"].items()
        if handler.get("class") == "logging.handlers.RotatingFileHandler"
    }


def test_parse_positive_int_uses_default_and_rejects_disabled_rotation():
    assert parse_positive_int(None, 100, name="LOG_FILE_MAX_BYTES") == 100
    assert parse_positive_int(" 2048 ", 100, name="LOG_FILE_MAX_BYTES") == 2048
    with pytest.raises(ValueError, match="LOG_FILE_MAX_BYTES"):
        parse_positive_int("0", 100, name="LOG_FILE_MAX_BYTES")
    with pytest.raises(ValueError, match="LOG_FILE_BACKUP_COUNT"):
        parse_positive_int("-1", 5, name="LOG_FILE_BACKUP_COUNT")


def test_parse_bool_and_log_level_use_defaults_and_reject_invalid_values():
    assert parse_bool(None, False, name="LOG_FILE_OUTPUT") is False
    assert parse_bool(" true ", True, name="LOG_FILE_OUTPUT") is True
    assert parse_bool("0", True, name="LOG_FILE_OUTPUT") is False
    with pytest.raises(ValueError, match="LOG_FILE_OUTPUT"):
        parse_bool("maybe", False, name="LOG_FILE_OUTPUT")

    assert parse_log_level(None) == DEFAULT_LOG_LEVEL == "INFO"
    assert parse_log_level(" debug ") == "DEBUG"
    assert parse_log_level("warn") == "WARNING"
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        parse_log_level("verbose")


def test_log_level_is_independent_of_django_debug():
    debug_on_info = build_logging_config(log_level="INFO", log_file_output=False)
    debug_off_debug = build_logging_config(log_level="DEBUG", log_file_output=False)
    assert debug_on_info["loggers"]["node"]["level"] == "INFO"
    assert debug_off_debug["loggers"]["node"]["level"] == "DEBUG"
    assert debug_on_info["loggers"]["node"]["handlers"] == ["console"]
    assert debug_off_debug["loggers"]["node"]["handlers"] == ["console"]


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


def test_default_logging_is_console_only_at_info():
    config = build_logging_config(log_level="INFO", log_file_output=False)
    assert _rotating_file_handlers(config) == {}
    for name in PRODUCT_APP_FILE_LOGGERS:
        logger_config = config["loggers"][name]
        assert logger_config["handlers"] == ["console"], name
        assert logger_config["level"] == "INFO", name
    assert config["loggers"]["celery"]["handlers"] == ["console"]
    assert config["loggers"]["celery"]["level"] == "INFO"
    assert config["loggers"]["django.db.backends"]["handlers"] == ["null"]
    assert "root" not in config["handlers"]
    assert "node" not in config["handlers"]


def test_all_rotating_file_handlers_share_default_rotation_limits():
    config = build_logging_config(log_level="INFO", log_file_output=True)
    rotating = _rotating_file_handlers(config)
    assert rotating
    for name, handler in rotating.items():
        assert handler["maxBytes"] == LOG_FILE_MAX_BYTES, name
        assert handler["backupCount"] == LOG_FILE_BACKUP_COUNT, name
        assert handler["maxBytes"] > 0, name
        assert handler["backupCount"] > 0, name


def test_product_app_loggers_keep_info_on_dedicated_rotating_files():
    config = build_logging_config(log_level="INFO", log_file_output=True)
    for name in PRODUCT_APP_FILE_LOGGERS:
        handler = config["handlers"][name]
        logger_config = config["loggers"][name]
        assert handler["class"] == "logging.handlers.RotatingFileHandler"
        assert handler["maxBytes"] > 0
        assert name in logger_config["handlers"]
        assert "console" in logger_config["handlers"]
        assert logger_config["level"] == "INFO"


def test_configured_node_handler_rolls_over_when_file_exceeds_max_bytes(tmp_path):
    cfg = build_logging_config(log_level="INFO", log_file_output=True)["handlers"]["node"]
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


def test_runtime_product_loggers_match_module_config():
    file_output_enabled = any(
        handler.get("class") == "logging.handlers.RotatingFileHandler" for handler in LOGGING["handlers"].values()
    )
    for name in PRODUCT_APP_FILE_LOGGERS:
        logger = logging.getLogger(name)
        expected_level = logging._nameToLevel[LOGGING["loggers"][name]["level"]]
        assert logger.getEffectiveLevel() == expected_level, name
        rotating = [handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)]
        if file_output_enabled:
            assert rotating, name
            assert rotating[0].maxBytes > 0, name
        else:
            assert rotating == [], name
            assert any(type(handler).__name__ == "SafeConsoleHandler" for handler in logger.handlers), name


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

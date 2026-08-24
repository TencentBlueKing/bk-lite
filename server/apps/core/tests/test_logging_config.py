import io
import logging
from pathlib import Path

from config.components.log import LOGGING, SafeConsoleHandler

SERVER_ROOT = Path(__file__).resolve().parents[3]


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

import logging
from pathlib import Path

from config.components.log import LOGGING


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

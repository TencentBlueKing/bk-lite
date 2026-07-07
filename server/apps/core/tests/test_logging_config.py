import logging

from config.components.log import LOGGING


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

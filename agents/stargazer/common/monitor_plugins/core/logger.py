# shim: redirect logger imports to stargazer's logging
import logging

monitor_logger = logging.getLogger("monitor")
logger = logging.getLogger("root")

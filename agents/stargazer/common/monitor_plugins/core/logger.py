# shim: redirect logger imports to stargazer's logging
import logging

from sanic.log import logger

monitor_logger = logging.getLogger("monitor")

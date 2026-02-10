import logging
from .handlers.plugin_handler import collect_plugin_task
from .handlers.monitor_handler import (
    collect_vmware_metrics_task,
    collect_qcloud_metrics_task,
)

logger = logging.getLogger(__name__)

__all__ = [
    "collect_plugin_task",
    "collect_vmware_metrics_task",
    "collect_qcloud_metrics_task",
]

try:
    from enterprise.tasks import collect_sangforscp_metrics_task

    __all__.append("collect_sangforscp_metrics_task")
    logger.info("Enterprise tasks loaded successfully")
except ImportError:
    collect_sangforscp_metrics_task = None
    logger.debug("Enterprise tasks not available, skipping")

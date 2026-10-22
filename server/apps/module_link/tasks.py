from celery import shared_task

from apps.core.logger import module_link_logger as logger
from apps.module_link.services.cmdb_monitor import CmdbMonitorTaskService
from apps.module_link.services.monitor_cmdb import MonitorCmdbTaskService

_RECYCLE_FAILED = "event=module_link_recycle_failed failed_stage=%s error_type=%s"
_SAFE_ERROR = "module link recycle failed"


@shared_task(max_retries=0)
def recycle_expired_cmdb_monitor_tasks():
    try:
        return CmdbMonitorTaskService.recycle_expired() + MonitorCmdbTaskService.recycle_expired()
    except Exception as exc:
        logger.error(
            _RECYCLE_FAILED,
            "recycle_expired",
            type(exc).__name__,
            exc_info=(type(exc), RuntimeError(_SAFE_ERROR), exc.__traceback__),
        )
        raise

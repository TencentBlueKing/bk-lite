from celery import shared_task

from apps.core.logger import module_link_logger as logger

_RECYCLE_FAILED = "event=module_link_recycle_failed failed_stage=%s error_type=%s"
_SAFE_ERROR = "module link recycle failed"


def _parents_installed() -> bool:
    from django.apps import apps

    return apps.is_installed("apps.cmdb") and apps.is_installed("apps.monitor")


@shared_task(max_retries=0)
def recycle_expired_cmdb_monitor_tasks():
    if not _parents_installed():
        return 0
    from apps.module_link.services.cmdb_monitor import CmdbMonitorTaskService
    from apps.module_link.services.monitor_cmdb import MonitorCmdbTaskService

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

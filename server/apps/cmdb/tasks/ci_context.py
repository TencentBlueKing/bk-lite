from celery import shared_task
from celery_singleton import Singleton


class _CiContextPendingSingleton(Singleton):
    """周期排空 CI 上下文待重算名单。锁会过期，避免任务卡在队列里时后续调度被永久丢掉。"""

    lock_expiry = 30 * 60
    raise_on_duplicate = False


@shared_task(base=_CiContextPendingSingleton)
def reconcile_ci_context_pending_task() -> dict:
    from apps.cmdb.services.ci_context import drain_ci_context_pending

    return drain_ci_context_pending()

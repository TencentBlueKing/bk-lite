"""集中声明队列，保留显式路由覆盖并对未知任务限频诊断。"""

from time import monotonic

from kombu import Exchange, Queue

from apps.core.celery_runtime.config import DEDICATED_QUEUES, POOL_IMPLEMENTATION
from apps.core.celery_runtime.manifest import TASK_ROUTES
from apps.core.logger import celery_logger as logger

QUEUE_NAMES = ("critical", "notification", "state", "background", "celery", *(q for queues in DEDICATED_QUEUES.values() for q in queues))
_last_warning = float("-inf")


def route_task(name, args=None, kwargs=None, options=None, **extra):
    global _last_warning
    queue = TASK_ROUTES.get(name)
    if queue is None:
        now = monotonic()
        if not name.startswith("celery.") and now - _last_warning >= 60:
            _last_warning = now
            try:
                logger.warning("Celery 出现未映射任务，将使用默认后台队列；请运行 celery_runtime_report 核对")
            except Exception:
                # 日志故障不能阻止原任务入队。
                return {"queue": "celery"}
        queue = "celery"
    return {"queue": queue}


def declared_queues():
    return tuple(Queue(name, Exchange(name, type="direct"), routing_key=name) for name in QUEUE_NAMES)


def configure_routes(app):
    app.conf.update(
        task_queues=declared_queues(),
        task_routes=(route_task,),
        task_default_queue="celery",
        worker_prefetch_multiplier=1,
        worker_pool=POOL_IMPLEMENTATION,
    )

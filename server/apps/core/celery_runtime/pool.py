"""可伸缩的 prefork 池，保留原 threads 对超时/子进程回收参数的有效行为。

只适配 Celery 执行池参数，不改 Task 声明、消息、ACK、重试和业务函数。
任务级超时原来不会在线程池中强制中断，此次迁移也不隐式启用。
"""

from celery.concurrency.prefork import TaskPool


class ThreadCompatiblePreforkPool(TaskPool):
    def __init__(self, *args, **options):
        for key in ("timeout", "soft_timeout", "maxtasksperchild", "max_memory_per_child"):
            options[key] = None
        super().__init__(*args, **options)

    def apply_async(self, target, args=None, kwargs=None, **options):
        # 同时覆盖新消息、重试、历史积压及 apply_async 显式传入的执行池超时。
        options.pop("timeout", None)
        options.pop("soft_timeout", None)
        return super().apply_async(target, args=args, kwargs=kwargs, **options)

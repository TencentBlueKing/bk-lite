"""Beat 读到未来的 last_run_at 时按当前时间续算，避免时钟回拨后周期任务永久不到期。"""

from datetime import timedelta

from django_celery_beat.schedulers import DatabaseScheduler, ModelEntry

from apps.core.logger import celery_logger as logger

FUTURE_LAST_RUN_TOLERANCE = timedelta(seconds=60)


class FutureLastRunModelEntry(ModelEntry):
    """上次运行时间超前超过容差时，本进程内先当成刚刚跑过。

    数据库里的原值留到任务真正执行。``__next__`` 会写成当时的当前时间。
    """

    def is_due(self):
        if self.model.enabled:
            self._release_future_last_run()
        return super().is_due()

    def _release_future_last_run(self):
        last_run_at = self.last_run_at
        if last_run_at is None:
            return
        now = self._default_now()
        if _as_utc(last_run_at) <= _as_utc(now) + FUTURE_LAST_RUN_TOLERANCE:
            return
        logger.warning(
            "event=celery_beat_future_last_run task=%s last_run_at=%s now=%s",
            self.name,
            last_run_at.isoformat(),
            now.isoformat(),
        )
        self.last_run_at = now


class FutureLastRunDatabaseScheduler(DatabaseScheduler):
    Entry = FutureLastRunModelEntry


def _as_utc(value):
    from datetime import timezone

    if value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

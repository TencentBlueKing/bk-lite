from django.db import models

from apps.core.models.time_info import TimeInfo


class AggregateMetricOrigin(TimeInfo):
    """各产品聚合序列首次出现的时间，按分钟对齐后持久化。"""

    product = models.CharField(max_length=16, unique=True)
    started_at = models.DateTimeField()

    class Meta:
        verbose_name = "聚合起点"
        verbose_name_plural = "聚合起点"

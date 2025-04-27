from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class ShowField(TimeInfo):
    created_by = models.CharField(db_index=True, max_length=50, verbose_name="创建人")
    model_id = models.CharField(db_index=True, max_length=100, verbose_name="模型ID")
    show_fields = JSONField(default=list, verbose_name="展示字段列表")

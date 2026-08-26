from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class CanvasDraftCheckpoint(TimeInfo):
    """显式「存一版」快照；每人每画布最多保留 HISTORY_LIMIT 条。"""

    resource_type = models.CharField(max_length=32)
    resource_id = models.PositiveIntegerField()
    username = models.CharField(max_length=255)
    label = models.CharField(max_length=30, blank=True, default="")
    payload = JSONField(default=dict)

    class Meta:
        db_table = "operation_analysis_canvas_draft_checkpoint"
        indexes = [
            models.Index(
                fields=["resource_type", "resource_id", "username", "id"],
                name="idx_canvas_draft_ckpt_owner",
            ),
        ]

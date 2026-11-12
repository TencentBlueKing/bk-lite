from django.db import models

DISPLAY_BACKFILL_STAGE = "display_backfill"


class CmdbRepairState(models.Model):
    """启动后一次性实例修复的阶段断点。完成后不再扫描。"""

    stage = models.CharField(max_length=200, unique=True)
    cursor = models.CharField(max_length=512, blank=True, default="")
    completed = models.BooleanField(default=False)
    fingerprint = models.CharField(max_length=4000, blank=True, default="")
    outcome = models.CharField(max_length=32, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "CMDB 实例修复断点"
        verbose_name_plural = verbose_name


def mark_display_backfill_dirty() -> None:
    CmdbRepairState.objects.update_or_create(
        stage=DISPLAY_BACKFILL_STAGE,
        defaults={"completed": False, "cursor": "", "outcome": ""},
    )


def mark_display_backfill_complete() -> None:
    CmdbRepairState.objects.update_or_create(
        stage=DISPLAY_BACKFILL_STAGE,
        defaults={"completed": True, "cursor": "", "outcome": ""},
    )

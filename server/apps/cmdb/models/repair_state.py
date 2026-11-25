from django.db import models

DISPLAY_BACKFILL_STAGE = "display_backfill"
CONFIG_FILE_ORPHAN_TEMP_STAGE = "config_file_orphan_temp"


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
    """清掉完成标记和游标，并推进代数。进行中的回填见到代数变化后放弃旧游标。"""
    row, created = CmdbRepairState.objects.get_or_create(
        stage=DISPLAY_BACKFILL_STAGE,
        defaults={"completed": False, "cursor": "", "outcome": "", "fingerprint": "1"},
    )
    if created:
        return
    try:
        generation = int(row.fingerprint or "0")
    except ValueError:
        generation = 0
    row.completed = False
    row.cursor = ""
    row.outcome = ""
    row.fingerprint = str(generation + 1)
    row.save(update_fields=["completed", "cursor", "outcome", "fingerprint", "updated_at"])


def mark_display_backfill_complete() -> None:
    CmdbRepairState.objects.update_or_create(
        stage=DISPLAY_BACKFILL_STAGE,
        defaults={"completed": True, "cursor": "", "outcome": ""},
    )

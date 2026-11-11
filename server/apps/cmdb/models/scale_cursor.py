from django.db import models


class CmdbScaleCursor(models.Model):
    """周期任务的续跑位置。锁释放后进度仍在。"""

    key = models.CharField(max_length=64, primary_key=True)
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cmdb_scale_cursor"

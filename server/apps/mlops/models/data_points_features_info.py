from django.db import models


class DataPointFeaturesInfo(models.Model):
    windows_size = models.IntegerField(
        default=30,
        verbose_name="",
        help_text="滚动窗口大小"
    )

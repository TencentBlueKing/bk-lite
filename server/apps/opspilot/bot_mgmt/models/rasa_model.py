from django.db import models
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo


class RasaModel(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="模型名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    model_file = models.FileField(
        verbose_name="文件",
        null=True,
        blank=True,
        storage=MinioBackend(bucket_name="munchkin-private"),
        upload_to="rasa_models",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "模型"
        verbose_name_plural = verbose_name
        db_table = "bot_mgmt_rasamodel"

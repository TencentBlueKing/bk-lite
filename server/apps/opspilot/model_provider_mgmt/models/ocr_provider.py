from django.db import models


class OCRProvider(models.Model):
    name = models.CharField(max_length=255, verbose_name="名称")
    ocr_config = models.JSONField(
        verbose_name="OCR配置",
        blank=True,
        null=True,
        default=dict,
    )
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=True, verbose_name="是否内置")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "OCR模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_ocrprovider"

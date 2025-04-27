from django.db import models
from django.utils.functional import cached_property

from apps.core.encoders import PrettyJSONEncoder
from apps.core.mixinx import EncryptMixin


class RerankModelChoices(models.TextChoices):
    LANG_SERVE = "langserve", "LangServe"


class RerankProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, unique=True, verbose_name="名称")
    rerank_model_type = models.CharField(max_length=255, choices=RerankModelChoices.choices, verbose_name="模型类型")
    rerank_config = models.JSONField(
        verbose_name="Rerank配置",
        blank=True,
        null=True,
        encoder=PrettyJSONEncoder,
        default=dict,
    )
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    @cached_property
    def decrypted_rerank_config_config(self):
        rerank_config_decrypted = self.rerank_config.copy()
        return rerank_config_decrypted

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rerank模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_rerankprovider"

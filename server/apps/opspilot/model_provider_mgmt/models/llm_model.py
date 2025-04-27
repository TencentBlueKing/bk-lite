from django.db import models
from django.utils.functional import cached_property

from apps.core.encoders import PrettyJSONEncoder
from apps.core.mixinx import EncryptMixin


class LLMModelChoices(models.TextChoices):
    CHAT_GPT = "chat-gpt", "OpenAI"
    ZHIPU = "zhipu", "智谱AI"
    HUGGING_FACE = "hugging_face", "Hugging Face"
    DEEP_SEEK = "deep-seek", "DeepSeek"


class LLMModel(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    llm_model_type = models.CharField(max_length=255, choices=LLMModelChoices.choices, verbose_name="LLM模型类型")
    llm_config = models.JSONField(
        verbose_name="LLM配置",
        blank=True,
        null=True,
        encoder=PrettyJSONEncoder,
        default=dict,
    )
    enabled = models.BooleanField(default=True, verbose_name="启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=True, verbose_name="是否内置")
    is_demo = models.BooleanField(default=False)
    consumer_team = models.CharField(default="", blank=True, null=True, max_length=64)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if "openai_api_key" in self.llm_config:
            self.encrypt_field("openai_api_key", self.llm_config)
        super().save(*args, **kwargs)

    @cached_property
    def decrypted_llm_config(self):
        llm_config_decrypted = self.llm_config.copy()

        if "openai_api_key" in llm_config_decrypted:
            self.decrypt_field("openai_api_key", llm_config_decrypted)
        return llm_config_decrypted

    class Meta:
        verbose_name = "LLM模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_llmmodel"

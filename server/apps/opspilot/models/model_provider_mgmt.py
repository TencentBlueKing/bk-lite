from django.db import models
from django.utils.functional import cached_property

from apps.core.encoders import PrettyJSONEncoder
from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.opspilot.enum import ActionChoice, SkillTypeChoices


class LLMModel(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
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
    model_type = models.ForeignKey("ModelType", on_delete=models.SET_NULL, verbose_name="模型类型", blank=True, null=True)
    label = models.CharField(max_length=100, verbose_name="标签", blank=True, null=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if "openai_api_key" in self.llm_config:
            self.decrypt_field("openai_api_key", self.llm_config)
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


class EmbedProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    embed_config = models.JSONField(
        verbose_name="嵌入配置",
        blank=True,
        null=True,
        encoder=PrettyJSONEncoder,
        default=dict,
    )
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    model_type = models.ForeignKey("ModelType", on_delete=models.SET_NULL, verbose_name="模型类型", blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Embed模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_embedprovider"

    def save(self, *args, **kwargs):
        if "api_key" in self.embed_config:
            self.decrypt_field("api_key", self.embed_config)
            self.encrypt_field("api_key", self.embed_config)
        super().save(*args, **kwargs)

    @cached_property
    def decrypted_embed_config(self):
        embed_config_decrypted = self.embed_config.copy()

        if "api_key" in embed_config_decrypted:
            self.decrypt_field("api_key", embed_config_decrypted)
        return embed_config_decrypted


class RerankProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
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
    model_type = models.ForeignKey("ModelType", on_delete=models.SET_NULL, verbose_name="模型类型", blank=True, null=True)

    def save(self, *args, **kwargs):
        if "api_key" in self.rerank_config:
            self.decrypt_field("api_key", self.rerank_config)
            self.encrypt_field("api_key", self.rerank_config)
        super().save(*args, **kwargs)

    @cached_property
    def decrypted_rerank_config_config(self):
        rerank_config_decrypted = self.rerank_config.copy()
        if "api_key" in rerank_config_decrypted:
            self.decrypt_field("api_key", rerank_config_decrypted)
        return rerank_config_decrypted

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rerank模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_rerankprovider"


class OCRProvider(models.Model, EncryptMixin):
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
    model_type = models.ForeignKey("ModelType", on_delete=models.SET_NULL, verbose_name="模型类型", blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "OCR模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_ocrprovider"

    def save(self, *args, **kwargs):
        if "api_key" in self.ocr_config:
            self.decrypt_field("api_key", self.ocr_config)
            self.encrypt_field("api_key", self.ocr_config)
        super().save(*args, **kwargs)


class LLMSkill(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="名称")
    llm_model = models.ForeignKey("LLMModel", on_delete=models.CASCADE, verbose_name="LLM模型", blank=True, null=True)
    skill_id = models.CharField(max_length=255, verbose_name="技能ID", blank=True, null=True)
    skill_prompt = models.TextField(blank=True, null=True, verbose_name="技能提示词")

    enable_conversation_history = models.BooleanField(default=False, verbose_name="启用对话历史")
    conversation_window_size = models.IntegerField(default=10, verbose_name="对话窗口大小")

    enable_rag = models.BooleanField(default=False, verbose_name="启用RAG")
    enable_rag_knowledge_source = models.BooleanField(default=False, verbose_name="显示RAG知识来源")
    rag_score_threshold_map = models.JSONField(default=dict, verbose_name="知识库RAG分数阈值映射")
    knowledge_base = models.ManyToManyField("KnowledgeBase", blank=True, verbose_name="知识库")
    introduction = models.TextField(blank=True, null=True, default="", verbose_name="介绍")
    team = models.JSONField(default=list, verbose_name="分组")

    show_think = models.BooleanField(default=True)
    tools = models.JSONField(default=list)

    temperature = models.FloatField(default=0.7, verbose_name="温度")
    skill_type = models.IntegerField(choices=SkillTypeChoices.choices, default=SkillTypeChoices.BASIC_TOOL, verbose_name="技能类型")
    enable_rag_strict_mode = models.BooleanField(default=False, verbose_name="启用RAG严格模式")
    is_template = models.BooleanField(default=False, verbose_name="是否模板")
    enable_km_route = models.BooleanField(default=False, verbose_name="启用知识库路由")
    km_llm_model = models.ForeignKey("LLMModel", on_delete=models.CASCADE, blank=True, null=True, related_name="km_llm_model")
    guide = models.TextField(default="", verbose_name="技能引导", blank=True, null=True)
    enable_suggest = models.BooleanField(default=False, verbose_name="启用建议")
    enable_query_rewrite = models.BooleanField(default=False, verbose_name="问题优化")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "LLM技能管理"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_llmskill"


class SkillTools(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=100, unique=True)
    params = models.JSONField(default=dict)
    team = models.JSONField(default=list)
    description = models.TextField()
    tags = models.JSONField(default=list)
    icon = models.CharField(max_length=100, default="")
    is_build_in = models.BooleanField(default=False)

    class Meta:
        db_table = "model_provider_mgmt_skilltools"


class SkillRule(MaintainerInfo, TimeInfo):
    skill = models.ForeignKey("LLMSkill", on_delete=models.CASCADE, verbose_name="技能")
    name = models.CharField(max_length=255, verbose_name="规则名称")
    description = models.TextField(blank=True, null=True, verbose_name="描述")
    condition = models.JSONField(default=dict, verbose_name="条件")
    action = models.IntegerField(default=0, verbose_name="动作", choices=ActionChoice.CHOICE)
    action_set = models.JSONField(default=dict, verbose_name="动作设置")
    is_enabled = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        db_table = "model_provider_mgmt_skillrule"


class SkillRequestLog(models.Model):
    skill = models.ForeignKey("LLMSkill", on_delete=models.CASCADE, verbose_name="技能")
    created_at = models.DateTimeField(auto_now_add=True)
    current_ip = models.GenericIPAddressField()
    state = models.BooleanField(default=True)
    request_detail = models.JSONField(default=dict)
    response_detail = models.JSONField(default=dict)
    user_message = models.TextField(default="")

    class Meta:
        db_table = "model_provider_mgmt_skillrequestlog"


class ModelType(models.Model):
    name = models.CharField(max_length=50, verbose_name="模型类型名称", unique=True)
    display_name = models.CharField(max_length=100, verbose_name="显示名称")
    icon = models.CharField(max_length=100, verbose_name="图标", blank=True, null=True)
    is_build_in = models.BooleanField(default=False)
    index = models.IntegerField(default=0, verbose_name="排序")
    tags = models.JSONField(default=list)

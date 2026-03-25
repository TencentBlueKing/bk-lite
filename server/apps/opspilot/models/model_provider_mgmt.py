import uuid

from django.db import models

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.opspilot.enum import SkillTypeChoices

VENDOR_TYPE_CHOICES = (
    ("openai", "OpenAI"),
    ("azure", "Azure"),
    ("aliyun", "阿里云"),
    ("zhipu", "智谱"),
    ("baidu", "百度"),
    ("anthropic", "Anthropic"),
    ("deepseek", "DeepSeek"),
    ("other", "其它"),
)


class ModelVendor(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    vendor_type = models.CharField(max_length=50, choices=VENDOR_TYPE_CHOICES, default="openai", verbose_name="供应商类型")
    api_base = models.CharField(max_length=500, blank=True, default="", verbose_name="API地址")
    api_key = models.TextField(blank=True, default="", verbose_name="API Key")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list, verbose_name="组织")
    description = models.TextField(blank=True, null=True, default="", verbose_name="简介")
    is_build_in = models.BooleanField(default=False)

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs):
        vendor_data = {"api_key": self.api_key}
        self.decrypt_field("api_key", vendor_data)
        self.encrypt_field("api_key", vendor_data)
        self.api_key = vendor_data["api_key"]
        super().save(*args, **kwargs)

    @property
    def decrypted_api_key(self):
        vendor_data = {"api_key": self.api_key}
        self.decrypt_field("api_key", vendor_data)
        return vendor_data["api_key"]

    class Meta:
        verbose_name = "供应商"
        verbose_name_plural = verbose_name
        db_table = "opspilot_modelvendor"


class LLMModel(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=True, verbose_name="是否内置")
    is_demo = models.BooleanField(default=False)
    vendor = models.ForeignKey(
        "ModelVendor",
        on_delete=models.SET_NULL,
        verbose_name="供应商",
        blank=True,
        null=True,
        related_name="llm_models",
    )
    model = models.CharField(max_length=255, verbose_name="模型", blank=True, null=True)
    label = models.CharField(max_length=100, verbose_name="标签", blank=True, null=True)

    def __str__(self) -> str:
        return str(self.name)

    @property
    def openai_api_key(self):
        return self.vendor.decrypted_api_key if self.vendor_id else ""

    @property
    def openai_api_base(self):
        return self.vendor.api_base if self.vendor_id else ""

    @property
    def model_name(self):
        return self.model or self.name

    class Meta:
        verbose_name = "LLM模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_llmmodel"


class EmbedProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    vendor = models.ForeignKey(
        "ModelVendor",
        on_delete=models.SET_NULL,
        verbose_name="供应商",
        blank=True,
        null=True,
        related_name="embed_models",
    )
    model = models.CharField(max_length=255, verbose_name="模型", blank=True, null=True)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "Embed模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_embedprovider"

    @property
    def api_key(self):
        return self.vendor.decrypted_api_key if self.vendor_id else ""

    @property
    def base_url(self):
        return self.vendor.api_base if self.vendor_id else ""

    @property
    def model_name(self):
        return self.model or self.name


class RerankProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")
    vendor = models.ForeignKey(
        "ModelVendor",
        on_delete=models.SET_NULL,
        verbose_name="供应商",
        blank=True,
        null=True,
        related_name="rerank_models",
    )
    model = models.CharField(max_length=255, verbose_name="模型", blank=True, null=True)

    @property
    def api_key(self):
        return self.vendor.decrypted_api_key if self.vendor_id else ""

    @property
    def base_url(self):
        return self.vendor.api_base if self.vendor_id else ""

    @property
    def model_name(self):
        return self.model or self.name

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "Rerank模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_rerankprovider"


class OCRProvider(models.Model, EncryptMixin):
    name = models.CharField(max_length=255, verbose_name="名称")
    enabled = models.BooleanField(default=True, verbose_name="是否启用")
    team = models.JSONField(default=list)
    is_build_in = models.BooleanField(default=True, verbose_name="是否内置")
    vendor = models.ForeignKey(
        "ModelVendor",
        on_delete=models.SET_NULL,
        verbose_name="供应商",
        blank=True,
        null=True,
        related_name="ocr_models",
    )
    model = models.CharField(max_length=255, verbose_name="模型", blank=True, null=True)

    def __str__(self) -> str:
        return str(self.name)

    class Meta:
        verbose_name = "OCR模型"
        verbose_name_plural = verbose_name
        db_table = "model_provider_mgmt_ocrprovider"

    @property
    def runtime_ocr_config(self):
        if self.vendor_id:
            if self.vendor.vendor_type == "azure":
                return {
                    "ocr_type": "azure_ocr",
                    "endpoint": self.vendor.api_base,
                    "api_key": self.vendor.decrypted_api_key,
                    "model": self.model or "",
                }
        return {
            "ocr_type": "olm_ocr",
            "base_url": self.vendor.api_base if self.vendor_id else "",
            "endpoint": self.vendor.api_base if self.vendor_id else "",
            "api_key": self.vendor.decrypted_api_key if self.vendor_id else "",
            "model": self.model or "olmOCR-7B-0225-preview",
        }


class LLMSkill(MaintainerInfo):
    name = models.CharField(max_length=255, verbose_name="名称")
    llm_model = models.ForeignKey(
        "LLMModel",
        on_delete=models.CASCADE,
        verbose_name="LLM模型",
        blank=True,
        null=True,
    )
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
    skill_type = models.IntegerField(
        choices=SkillTypeChoices.choices,
        default=SkillTypeChoices.BASIC_TOOL,
        verbose_name="技能类型",
    )
    enable_rag_strict_mode = models.BooleanField(default=False, verbose_name="启用RAG严格模式")
    is_template = models.BooleanField(default=False, verbose_name="是否模板")
    enable_km_route = models.BooleanField(default=False, verbose_name="启用知识库路由")
    km_llm_model = models.ForeignKey(
        "LLMModel",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="km_llm_model",
    )
    guide = models.TextField(default="", verbose_name="技能引导", blank=True, null=True)
    enable_suggest = models.BooleanField(default=False, verbose_name="启用建议")
    enable_query_rewrite = models.BooleanField(default=False, verbose_name="问题优化")
    instance_id = models.CharField(max_length=36, blank=True, null=True, verbose_name="实例ID", db_index=True)
    is_builtin = models.BooleanField(default=False, verbose_name="是否内置", db_index=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 如果instance_id为空，自动生成UUID
        if not self.instance_id:
            self.instance_id = str(uuid.uuid4())
        super().save(*args, **kwargs)

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
    tools = models.JSONField(default=list)

    class Meta:
        db_table = "model_provider_mgmt_skilltools"


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

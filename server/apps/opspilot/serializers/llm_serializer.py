from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.models import LLMModel, LLMSkill, SkillRequestLog, SkillTools, UserPin
from apps.opspilot.serializers.model_vendor_serializer import CustomProviderSerializer


class LLMModelSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.llm_model"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if not attrs.get("vendor") and not getattr(self.instance, "vendor_id", None):
            raise serializers.ValidationError({"vendor": "供应商不能为空"})
        if not attrs.get("model") and not getattr(self.instance, "model", None):
            raise serializers.ValidationError({"model": "模型不能为空"})
        return attrs

    class Meta:
        model = LLMModel
        fields = "__all__"


class LLMSerializer(TeamSerializer, AuthSerializer):
    permission_key = "skill"

    rag_score_threshold = serializers.SerializerMethodField()
    llm_model_name = serializers.SerializerMethodField()
    is_pinned = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.pinned_skill_ids = set()
        request = self.context.get("request")
        if not request or not request.user:
            return
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        self.pinned_skill_ids = set(
            UserPin.objects.filter(
                username=username,
                domain=domain,
                content_type=UserPin.CONTENT_TYPE_SKILL,
            ).values_list("object_id", flat=True)
        )

    class Meta:
        model = LLMSkill
        fields = "__all__"

    @staticmethod
    def get_rag_score_threshold(instance: LLMSkill):
        return [{"knowledge_base": k, "score": v} for k, v in instance.rag_score_threshold_map.items()]

    def get_llm_model_name(self, instance: LLMSkill):
        return instance.llm_model.name if instance.llm_model is not None else ""

    def get_is_pinned(self, instance: LLMSkill) -> bool:
        """获取当前用户对此 LLMSkill 的置顶状态"""
        return instance.id in self.pinned_skill_ids


class SkillRequestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillRequestLog
        fields = "__all__"


class SkillToolsSerializer(AuthSerializer):
    permission_key = "tools"

    description_tr = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()

    class Meta:
        model = SkillTools
        fields = "__all__"

    def _get_language_loader(self):
        """获取语言加载器，根据请求的用户语言设置"""
        request = self.context.get("request")
        locale = "en"  # 默认语言
        if request and hasattr(request, "user") and request.user:
            locale = getattr(request.user, "locale", "en") or "en"
        return LanguageLoader(app="opspilot", default_lang=locale)

    def get_description_tr(self, instance: SkillTools):
        """获取翻译后的工具集描述"""
        loader = self._get_language_loader()

        # 尝试从语言文件获取翻译，使用 name 作为 key
        translated = loader.get(f"tools.{instance.name}.description")
        if translated:
            return translated

        # fallback 到原始描述
        return instance.description

    def get_tools(self, instance: SkillTools):
        """获取翻译后的子工具列表（覆盖原始 tools 字段）"""
        return self._get_translated_tools(instance)

    def _get_translated_tools(self, instance: SkillTools):
        """翻译子工具列表的通用方法"""
        loader = self._get_language_loader()
        tools = instance.tools or []
        translated_tools = []

        for tool in tools:
            tool_name = tool.get("name", "")
            original_description = tool.get("description", "")

            # 尝试从语言文件获取子工具的翻译
            # 翻译键格式: tools.{parent_tool_name}.tools.{sub_tool_name}.description
            translated_description = loader.get(f"tools.{instance.name}.tools.{tool_name}.description")

            translated_tool = tool.copy()
            translated_tool["description"] = translated_description if translated_description else original_description
            translated_tools.append(translated_tool)

        return translated_tools

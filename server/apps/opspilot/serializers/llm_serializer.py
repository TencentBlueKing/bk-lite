from rest_framework import serializers

from apps.core.utils.loader import LanguageLoader
from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.models import LLMModel, LLMSkill, SkillRequestLog, SkillTools
from apps.opspilot.serializers.model_type_serializer import CustomProviderSerializer


class LLMModelSerializer(AuthSerializer, CustomProviderSerializer):
    permission_key = "provider.llm_model"

    class Meta:
        model = LLMModel
        fields = "__all__"


class LLMSerializer(TeamSerializer, AuthSerializer):
    permission_key = "skill"

    rag_score_threshold = serializers.SerializerMethodField()
    llm_model_name = serializers.SerializerMethodField()

    class Meta:
        model = LLMSkill
        fields = "__all__"

    @staticmethod
    def get_rag_score_threshold(instance: LLMSkill):
        return [{"knowledge_base": k, "score": v} for k, v in instance.rag_score_threshold_map.items()]

    def get_llm_model_name(self, instance: LLMSkill):
        return instance.llm_model.name if instance.llm_model is not None else ""


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

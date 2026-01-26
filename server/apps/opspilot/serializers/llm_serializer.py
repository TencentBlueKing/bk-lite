from rest_framework import serializers

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

    # TODO: 后续需要针对内置 tools 进行中英文翻译，使用 LanguageLoader 替代 gettext
    # 需要在 opspilot/language/*.yaml 中添加内置工具的描述翻译
    description_tr = serializers.SerializerMethodField()

    class Meta:
        model = SkillTools
        fields = "__all__"

    @staticmethod
    def get_description_tr(instance: SkillTools):
        # 暂时直接返回原始描述，不进行翻译
        return instance.description

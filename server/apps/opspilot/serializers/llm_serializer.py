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
        fields = [
            "id",
            "name",
            "enabled",
            "team",
            "is_build_in",
            "is_demo",
            "vendor",
            "model",
            "label",
            # 只读派生字段（保持现有读取输出不变）
            "permissions",
            "team_name",
            "vendor_name",
            "vendor_type",
        ]


class LLMSerializer(TeamSerializer, AuthSerializer):
    permission_key = "skill"

    llm_model_name = serializers.SerializerMethodField()
    is_pinned = serializers.SerializerMethodField()
    skill_params = serializers.SerializerMethodField()

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
        fields = [
            "id",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "llm_model",
            "skill_id",
            "skill_prompt",
            "enable_conversation_history",
            "conversation_window_size",
            "introduction",
            "team",
            "show_think",
            "tools",
            "skill_params",
            "temperature",
            "skill_type",
            "is_template",
            "guide",
            "enable_suggest",
            "enable_query_rewrite",
            "instance_id",
            "is_builtin",
            "wiki_knowledge_bases",
            # 只读派生字段（保持现有读取输出不变）
            "permissions",
            "team_name",
            "llm_model_name",
            "is_pinned",
        ]
        # F017: 系统/审计字段标记为只读，防止通过 create/update 的请求体
        # 被客户端篡改（mass-assignment）。这些字段由服务端在 perform_create/
        # perform_update 中显式写入，输出表现不变。
        read_only_fields = [
            "id",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "is_builtin",
        ]

    def get_llm_model_name(self, instance: LLMSkill):
        return instance.llm_model.name if instance.llm_model is not None else ""

    def get_is_pinned(self, instance: LLMSkill) -> bool:
        """获取当前用户对此 LLMSkill 的置顶状态"""
        return instance.id in self.pinned_skill_ids

    @staticmethod
    def get_skill_params(instance: LLMSkill):
        """返回技能参数列表，password 类型的 value 掩码为 '******'"""
        params = instance.skill_params or []
        result = []
        for param in params:
            item = dict(param)
            if item.get("type") == "password":
                item["value"] = "******"
            result.append(item)
        return result


class SkillRequestLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillRequestLog
        fields = [
            "id",
            "skill",
            "created_at",
            "current_ip",
            "state",
            "request_detail",
            "response_detail",
            "user_message",
        ]


class SkillToolsSerializer(AuthSerializer):
    permission_key = "tools"

    description_tr = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()

    class Meta:
        model = SkillTools
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "domain",
            "updated_by_domain",
            "name",
            "params",
            "team",
            "description",
            "tags",
            "icon",
            "is_build_in",
            "tools",
            # 只读派生字段（保持现有读取输出不变）
            "permissions",
            "description_tr",
            "display_name",
        ]

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

    def get_display_name(self, instance: SkillTools):
        """获取翻译后的工具集展示名称。

        内置工具的 ``name`` 字段被当作 ID 使用（如 ``current_time``、``mysql``），
        前端展示需要一个可读且支持中英文切换的名称。这里复用 language 目录下的
        yaml 翻译映射（``tools.{name}.name``），未配置翻译时回退到 ``name``。
        """
        loader = self._get_language_loader()
        translated = loader.get(f"tools.{instance.name}.name")
        if translated:
            return translated

        # fallback 到原始 name（自定义 MCP 工具通常没有翻译映射）
        return instance.name

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

from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.enum import BotTypeChoice
from apps.opspilot.models import Bot, UserPin
from apps.opspilot.utils.workflow_sensitive_config import mask_workflow_sensitive_config


class BotSerializer(TeamSerializer, AuthSerializer):
    permission_key = "bot"

    is_pinned = serializers.SerializerMethodField()
    usage_team_name = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        self.pinned_bot_ids = set()
        request = self.context.get("request")
        if not request or not request.user:
            return
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        self.pinned_bot_ids = set(
            UserPin.objects.filter(username=username, domain=domain, content_type=UserPin.CONTENT_TYPE_BOT).values_list("object_id", flat=True)
        )

    class Meta:
        model = Bot
        fields = "__all__"
        # api_token 是敏感凭证，仅允许写入、禁止在响应中回显（其余字段保持原样）
        extra_kwargs = {"api_token": {"write_only": True}}

    def get_is_pinned(self, instance: Bot) -> bool:
        """获取当前用户对此 Bot 的置顶状态"""
        return instance.id in self.pinned_bot_ids

    def get_usage_team_name(self, instance: Bot):
        """使用组织 id → 名称（与 team_name 同款，基于当前用户 group_list）"""
        return [self.group_map.get(i) for i in (instance.usage_team or []) if i in self.group_map]

    def get_fields(self):
        """根据操作类型动态返回字段"""
        fields = super().get_fields()

        # 获取视图上下文
        view = self.context.get("view")

        # 如果是列表操作，只返回部分字段
        if view and hasattr(view, "action") and view.action == "retrieve":
            fields.update({"workflow_data": serializers.SerializerMethodField()})

            # 详情操作返回所有字段
        return fields

    @staticmethod
    def get_workflow_data(instance: Bot):
        if instance.bot_type == BotTypeChoice.CHAT_FLOW:
            workflow = instance.botworkflow_set.first()
            if not workflow:
                return {}
            return mask_workflow_sensitive_config(workflow.web_json)
        return {}

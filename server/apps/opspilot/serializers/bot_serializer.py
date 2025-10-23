from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer, TeamSerializer
from apps.opspilot.enum import BotTypeChoice
from apps.opspilot.models import Bot


class BotSerializer(TeamSerializer, AuthSerializer):
    permission_key = "bot"

    class Meta:
        model = Bot
        fields = "__all__"

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
            return workflow.web_json
        return {}

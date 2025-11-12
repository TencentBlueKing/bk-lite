from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import OperationLog


class OperationLogSerializer(serializers.ModelSerializer):
    """操作日志序列化器"""

    action_type_display = serializers.SerializerMethodField()
    operation_time = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = OperationLog
        fields = "__all__"

    def __init__(self, instance=None, data=empty, **kwargs):
        super(OperationLogSerializer, self).__init__(instance, data, **kwargs)
        locale = getattr(self.context.get("request").user, "locale", "en") if self.context.get("request") else "en"
        self.loader = LanguageLoader(app="system_mgmt", default_lang=locale)

    def get_action_type_display(self, obj):
        """获取操作类型的翻译显示"""
        action_map = {
            OperationLog.ACTION_CREATE: self.loader.get("action_type.create") or "Create",
            OperationLog.ACTION_UPDATE: self.loader.get("action_type.update") or "Update",
            OperationLog.ACTION_DELETE: self.loader.get("action_type.delete") or "Delete",
            OperationLog.ACTION_EXECUTE: self.loader.get("action_type.execute") or "Execute",
        }
        return action_map.get(obj.action_type, obj.get_action_type_display())

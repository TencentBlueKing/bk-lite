from rest_framework import serializers

from apps.opspilot.models import WorkFlowTaskResult


class WorkFlowTaskResultSerializer(serializers.ModelSerializer):
    """工作流任务执行结果序列化器"""

    class Meta:
        model = WorkFlowTaskResult
        fields = "__all__"

from rest_framework import serializers

from apps.opspilot.models import WorkFlowTaskResult


class WorkFlowTaskResultSerializer(serializers.ModelSerializer):
    """工作流任务执行结果序列化器"""

    duration_ms = serializers.SerializerMethodField(help_text="耗时（毫秒）")

    class Meta:
        model = WorkFlowTaskResult
        fields = [
            "id",
            "bot_work_flow",
            "execution_id",
            "run_time",
            "finished_at",
            "status",
            "input_data",
            "output_data",
            "last_output",
            "execute_type",
            "duration_ms",
        ]
        read_only_fields = fields

    def get_duration_ms(self, obj) -> int | None:
        if obj.run_time and obj.finished_at:
            return int((obj.finished_at - obj.run_time).total_seconds() * 1000)
        return None

from rest_framework import serializers

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
)


class DashboardReportExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportExecution
        fields = [
            "id",
            "subscription",
            "dashboard",
            "creator",
            "status",
            "trigger_type",
            "failure_stage",
            "error_message",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields

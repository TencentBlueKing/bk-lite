from rest_framework import serializers

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
)


class DashboardReportExecutionSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportExecutionSnapshot
        fields = [
            "dashboard_id",
            "creator_id",
            "subscription_id",
            "filter_values",
            "created_at",
        ]
        read_only_fields = fields


class DashboardReportExecutionSerializer(serializers.ModelSerializer):
    snapshot = DashboardReportExecutionSnapshotSerializer(read_only=True)

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
            "snapshot",
        ]
        read_only_fields = fields

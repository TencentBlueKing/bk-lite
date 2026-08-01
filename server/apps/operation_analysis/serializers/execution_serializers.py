from rest_framework import serializers

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportExecutionSnapshot,
    DashboardReportPdfArtifact,
    DashboardReportRenderSnapshot,
)


class DashboardReportExecutionSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportExecutionSnapshot
        fields = [
            "dashboard_id",
            "creator_id",
            "creator_timezone",
            "subscription_id",
            "subscription_name",
            "recipient_email",
            "trigger_type",
            "email_channel_id",
            "scheduled_time_utc",
            "schedule_timezone",
            "scheduled_local_time",
            "subscription_version",
            "filter_values",
            "filter_semantics",
            "created_at",
        ]
        read_only_fields = fields


class DashboardReportRenderSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportRenderSnapshot
        fields = [
            "dashboard_id",
            "dashboard_name",
            "dashboard_updated_at",
            "view_sets",
            "filters",
            "other",
            "widget_manifest",
            "datasource_snapshots",
            "created_at",
        ]
        read_only_fields = fields


class DashboardReportPdfArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportPdfArtifact
        fields = [
            "storage_reference",
            "filename",
            "size_bytes",
            "sha256",
            "created_at",
            "expires_at",
        ]
        read_only_fields = fields


class DashboardReportExecutionSerializer(serializers.ModelSerializer):
    snapshot = DashboardReportExecutionSnapshotSerializer(read_only=True)
    pdf_artifact = DashboardReportPdfArtifactSerializer(read_only=True)

    class Meta:
        model = DashboardReportExecution
        fields = [
            "id",
            "subscription",
            "dashboard",
            "creator",
            "status",
            "trigger_type",
            "request_id",
            "scheduled_time_utc",
            "failure_stage",
            "error_code",
            "error_message",
            "attempt_count",
            "source_canvas_deleted_during_execution",
            "created_at",
            "started_at",
            "finished_at",
            "snapshot",
            "pdf_artifact",
        ]
        read_only_fields = fields

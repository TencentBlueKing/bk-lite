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
            "resource_type",
            "resource_id",
            "resource_display_label",
            "creator_id",
            "creator_domain",
            "creator_timezone",
            "subscription_id",
            "subscription_name",
            "recipient_email",
            "trigger_type",
            "email_channel_id",
            "execution_team_id",
            "scheduled_time_utc",
            "schedule_timezone",
            "scheduled_local_time",
            "subscription_version",
            "subscription_revision",
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
            "resource_type",
            "resource_id",
            "resource_display_label",
            "render_schema_version",
            "view_sets",
            "filters",
            "other",
            "widget_manifest",
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
            "resource_type",
            "resource_id",
            "creator",
            "creator_domain",
            "status",
            "trigger_type",
            "request_id",
            "scheduled_time_utc",
            "failure_stage",
            "error_code",
            "error_message",
            "attempt_count",
            "delivery_outcome",
            "delivered_at",
            "reconciled_from_status",
            "reconciliation_reason",
            "reconciliation_source",
            "reconciled_at",
            "source_canvas_deleted_during_execution",
            "created_at",
            "started_at",
            "finished_at",
            "snapshot",
            "pdf_artifact",
        ]
        read_only_fields = fields

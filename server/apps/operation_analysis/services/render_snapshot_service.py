from django.db import transaction

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportRenderSnapshot,
)
from apps.operation_analysis.services.canvas_report.registry import (
    get_canvas_report_adapter,
)
from apps.operation_analysis.services.canvas_report.types import (
    DEFAULT_RENDER_SCHEMA_VERSION,
    RESOURCE_TYPE_DASHBOARD,
)


class DashboardReportRenderSnapshotService:
    @classmethod
    def create(
        cls,
        execution: DashboardReportExecution,
    ) -> DashboardReportRenderSnapshot:
        try:
            return execution.render_snapshot
        except DashboardReportRenderSnapshot.DoesNotExist:
            pass

        resource_type = execution.resource_type or RESOURCE_TYPE_DASHBOARD
        resource_id = (
            execution.resource_id
            if execution.resource_id is not None
            else execution.dashboard_id
        )
        if resource_id is None:
            raise ValueError("画布资源不存在")

        adapter = get_canvas_report_adapter(resource_type)
        resource = adapter.load_resource(resource_id)
        fields = adapter.build_render_snapshot_fields(resource)
        fields["resource_type"] = resource_type
        fields["resource_id"] = resource_id
        fields["render_schema_version"] = DEFAULT_RENDER_SCHEMA_VERSION
        with transaction.atomic():
            return DashboardReportRenderSnapshot.objects.create(
                execution=execution,
                **fields,
            )

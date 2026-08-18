from copy import deepcopy

from apps.operation_analysis.models.models import Report
from apps.operation_analysis.services.canvas_report.types import RESOURCE_TYPE_REPORT

TERMINATION_REASON_REPORT_DELETED = "report_deleted"


def build_report_widget_manifest(view_sets) -> list[dict]:
    """从 Report view_sets.sections 收集 widget→datasource 清单。"""
    if not isinstance(view_sets, dict):
        return []
    sections = view_sets.get("sections") or []
    manifest: list[dict] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        value_config = section.get("valueConfig") or {}
        widget_id = section.get("id")
        if widget_id is None:
            continue
        manifest.append(
            {
                "widget_id": widget_id,
                "widget_type": value_config.get("chartType"),
                "datasource_id": value_config.get("dataSource"),
            }
        )
    return manifest


class ReportCanvasReportAdapter:
    resource_type = RESOURCE_TYPE_REPORT

    def load_resource(self, resource_id: int) -> Report:
        return Report.objects.get(pk=resource_id)

    def build_manifest(self, resource: Report) -> list[dict]:
        return build_report_widget_manifest(resource.view_sets or {})

    def load_filters(self, resource: Report):
        view_sets = resource.view_sets or {}
        if not isinstance(view_sets, dict):
            return []
        return deepcopy(view_sets.get("filters") or [])

    def build_render_snapshot_fields(self, resource: Report) -> dict:
        view_sets = deepcopy(resource.view_sets or {})
        if not isinstance(view_sets, dict):
            view_sets = {}
        return {
            "dashboard_id": None,
            "dashboard_name": resource.name,
            "dashboard_updated_at": resource.updated_at,
            "resource_display_label": self.resource_display_label(),
            "view_sets": view_sets,
            "filters": self.load_filters(resource),
            "other": deepcopy(resource.other),
            "widget_manifest": build_report_widget_manifest(view_sets),
        }

    def render_route_key(self) -> str:
        return "report"

    def resource_display_label(self) -> str:
        return "报表"

    def can_view_resource(
        self,
        user,
        resource: Report,
        *,
        team_id: int,
        include_children: bool = False,
    ) -> bool:
        from apps.operation_analysis.services.canvas_report.permissions import can_view_canvas

        return can_view_canvas(
            user,
            self.resource_type,
            resource.id,
            team_id=team_id,
            include_children=include_children,
        )

    def terminate_subscriptions_on_delete(
        self,
        resource: Report,
        *,
        actor: str,
        actor_domain: str = "",
    ) -> int:
        from apps.operation_analysis.services.subscription_service import DashboardSubscriptionService

        return DashboardSubscriptionService.terminate_for_resource_deletion(
            resource_type=RESOURCE_TYPE_REPORT,
            resource_id=resource.pk,
            actor=actor,
            actor_domain=actor_domain,
            reason=TERMINATION_REASON_REPORT_DELETED,
        )

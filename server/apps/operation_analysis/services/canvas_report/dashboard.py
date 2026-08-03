from copy import deepcopy

from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_DASHBOARD,
)


def build_dashboard_widget_manifest(view_sets: list) -> list[dict]:
    """从 Dashboard view_sets 树收集 widget→datasource 清单。"""
    manifest: list[dict] = []

    def collect(items):
        for item in items:
            if not isinstance(item, dict):
                continue
            children = (item.get("subGridOpts") or {}).get("children") or []
            if children:
                collect(children)
            if item.get("itemType") == "group":
                continue

            value_config = item.get("valueConfig") or {}
            widget_id = item.get("id", item.get("i"))
            if widget_id is None:
                continue
            manifest.append(
                {
                    "widget_id": widget_id,
                    "widget_type": value_config.get(
                        "chartType",
                        item.get("chartType"),
                    ),
                    "datasource_id": value_config.get(
                        "dataSource",
                        item.get("dataSource"),
                    ),
                }
            )

    collect(view_sets)
    return manifest


class DashboardCanvasReportAdapter:
    resource_type = RESOURCE_TYPE_DASHBOARD

    def load_resource(self, resource_id: int) -> Dashboard:
        return Dashboard.objects.get(pk=resource_id)

    def build_manifest(self, resource: Dashboard) -> list[dict]:
        return build_dashboard_widget_manifest(resource.view_sets or [])

    def load_filters(self, resource: Dashboard):
        return deepcopy(resource.filters)

    def build_render_snapshot_fields(self, resource: Dashboard) -> dict:
        view_sets = deepcopy(resource.view_sets or [])
        return {
            "dashboard_id": resource.id,
            "dashboard_name": resource.name,
            "dashboard_updated_at": resource.updated_at,
            "resource_display_label": self.resource_display_label(),
            "view_sets": view_sets,
            "filters": self.load_filters(resource),
            "other": deepcopy(resource.other),
            "widget_manifest": build_dashboard_widget_manifest(view_sets),
        }

    def render_route_key(self) -> str:
        return "dashboard"

    def resource_display_label(self) -> str:
        return "仪表盘"

    def can_view_resource(
        self,
        user,
        resource: Dashboard,
        *,
        team_id: int,
        include_children: bool = False,
    ) -> bool:
        from apps.operation_analysis.services.canvas_report.permissions import (
            can_view_canvas,
        )

        return can_view_canvas(
            user,
            self.resource_type,
            resource.id,
            team_id=team_id,
            include_children=include_children,
        )

    def terminate_subscriptions_on_delete(
        self,
        resource: Dashboard,
        *,
        actor: str,
        actor_domain: str = "",
    ) -> int:
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )

        return DashboardSubscriptionService.terminate_for_dashboard_deletion(
            resource,
            actor=actor,
            actor_domain=actor_domain,
        )

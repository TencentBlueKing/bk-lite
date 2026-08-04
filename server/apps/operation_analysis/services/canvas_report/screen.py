from copy import deepcopy

from apps.operation_analysis.models.models import Screen
from apps.operation_analysis.services.canvas_report.types import (
    RESOURCE_TYPE_SCREEN,
)

TERMINATION_REASON_SCREEN_DELETED = "screen_deleted"


def build_screen_widget_manifest(view_sets) -> list[dict]:
    """从 Screen view_sets.items 收集 widget→datasource 清单。"""
    if not isinstance(view_sets, dict):
        return []
    items = view_sets.get("items") or []
    manifest: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
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
    return manifest


class ScreenCanvasReportAdapter:
    resource_type = RESOURCE_TYPE_SCREEN

    def load_resource(self, resource_id: int) -> Screen:
        return Screen.objects.get(pk=resource_id)

    def build_manifest(self, resource: Screen) -> list[dict]:
        return build_screen_widget_manifest(resource.view_sets or {})

    def load_filters(self, resource: Screen):
        view_sets = resource.view_sets or {}
        if not isinstance(view_sets, dict):
            return []
        return deepcopy(view_sets.get("filters") or [])

    def build_render_snapshot_fields(self, resource: Screen) -> dict:
        view_sets = deepcopy(resource.view_sets or {})
        if not isinstance(view_sets, dict):
            view_sets = {}
        return {
            # Screen 无 Dashboard FK；兼容列仅承载展示名/时间
            "dashboard_id": None,
            "dashboard_name": resource.name,
            "dashboard_updated_at": resource.updated_at,
            "resource_display_label": self.resource_display_label(),
            "view_sets": view_sets,
            "filters": self.load_filters(resource),
            "other": deepcopy(resource.other),
            "widget_manifest": build_screen_widget_manifest(view_sets),
        }

    def render_route_key(self) -> str:
        return "screen"

    def resource_display_label(self) -> str:
        return "大屏"

    def can_view_resource(
        self,
        user,
        resource: Screen,
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
        resource: Screen,
        *,
        actor: str,
        actor_domain: str = "",
    ) -> int:
        from apps.operation_analysis.services.subscription_service import (
            DashboardSubscriptionService,
        )

        return DashboardSubscriptionService.terminate_for_resource_deletion(
            resource_type=RESOURCE_TYPE_SCREEN,
            resource_id=resource.pk,
            actor=actor,
            actor_domain=actor_domain,
            reason=TERMINATION_REASON_SCREEN_DELETED,
        )

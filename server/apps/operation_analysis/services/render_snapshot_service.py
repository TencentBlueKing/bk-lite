from copy import deepcopy

from django.db import transaction

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportRenderSnapshot,
)


def _widget_manifest(view_sets: list) -> list[dict]:
    manifest = []

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


class DashboardReportRenderSnapshotService:
    @classmethod
    def create(
        cls,
        execution: DashboardReportExecution,
    ) -> DashboardReportRenderSnapshot:
        dashboard = execution.dashboard
        if dashboard is None:
            raise ValueError("Dashboard 不存在")

        view_sets = deepcopy(dashboard.view_sets or [])
        with transaction.atomic():
            return DashboardReportRenderSnapshot.objects.create(
                execution=execution,
                dashboard_id=dashboard.id,
                dashboard_name=dashboard.name,
                dashboard_updated_at=dashboard.updated_at,
                view_sets=view_sets,
                filters=deepcopy(dashboard.filters),
                other=deepcopy(dashboard.other),
                widget_manifest=_widget_manifest(view_sets),
            )

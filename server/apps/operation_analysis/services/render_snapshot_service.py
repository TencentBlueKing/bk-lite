from copy import deepcopy

from django.db import transaction

from apps.operation_analysis.models.datasource_models import (
    DataSourceAPIModel,
)
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


def _datasource_snapshots(widget_manifest: list[dict]) -> list[dict]:
    """Persist a non-sensitive DataSource audit freeze for the execution.

    Current MVP render/query still loads live DataSource definitions. This
    snapshot is immutable after create and is not consumed by the render path.
    """
    ds_ids = {
        entry["datasource_id"]
        for entry in widget_manifest
        if entry.get("datasource_id") is not None
    }
    if not ds_ids:
        return []

    snapshots = []
    for ds in DataSourceAPIModel.objects.filter(id__in=ds_ids).only(
        "id", "source_type", "query_config", "field_schema",
    ):
        snapshots.append(
            {
                "datasource_id": ds.id,
                "source_type": ds.source_type,
                "query_config": deepcopy(ds.query_config or {}),
                "field_schema": deepcopy(ds.field_schema or []),
            }
        )
    return snapshots


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

        dashboard = execution.dashboard
        if dashboard is None:
            raise ValueError("Dashboard 不存在")

        view_sets = deepcopy(dashboard.view_sets or [])
        manifest = _widget_manifest(view_sets)
        with transaction.atomic():
            return DashboardReportRenderSnapshot.objects.create(
                execution=execution,
                dashboard_id=dashboard.id,
                dashboard_name=dashboard.name,
                dashboard_updated_at=dashboard.updated_at,
                view_sets=view_sets,
                filters=deepcopy(dashboard.filters),
                other=deepcopy(dashboard.other),
                widget_manifest=manifest,
                datasource_snapshots=_datasource_snapshots(manifest),
            )

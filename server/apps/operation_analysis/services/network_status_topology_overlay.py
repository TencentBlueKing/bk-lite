from __future__ import annotations

from apps.operation_analysis.services.named_option_datasources import _resolve_unique_rest_api_ids

NETWORK_STATUS_TOPOLOGY_CHART_TYPE = "networkStatusTopology"
NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS = (
    "cmdb/get_monitor_ids_by_inst_uuids",
    "monitor/query_latest_active_alerts",
    "monitor/query_latest_interface_metrics",
)
NETWORK_STATUS_TOPOLOGY_OVERLAY_QUERY_KEYS = frozenset({"inst_uuids", "instance_ids", "instance_id", "limit"})


def collect_network_status_topology_overlay_datasource_ids() -> set[int]:
    resolved = _resolve_unique_rest_api_ids(set(NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS))
    return {ds_id for ds_id in resolved.values() if ds_id is not None}


def view_sets_has_network_status_topology(value) -> bool:
    if isinstance(value, list):
        return any(view_sets_has_network_status_topology(item) for item in value)
    if not isinstance(value, dict):
        return False
    value_config = value.get("valueConfig") if isinstance(value.get("valueConfig"), dict) else {}
    chart_type = value_config.get("chartType") or value.get("chartType")
    if chart_type == NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
        return True
    if value_config.get("sceneWidgetType") == NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
        return True
    return any(view_sets_has_network_status_topology(child) for child in value.values())


def overlay_datasource_ids_for_view_sets(view_sets) -> set[int]:
    if not view_sets_has_network_status_topology(view_sets):
        return set()
    return collect_network_status_topology_overlay_datasource_ids()


def expand_widget_manifest_with_topology_overlay(manifest: list[dict] | None) -> list[dict]:
    if not manifest:
        return list(manifest or [])
    overlay_ids = collect_network_status_topology_overlay_datasource_ids()
    expanded: list[dict] = []
    seen = set()
    for item in manifest:
        if not isinstance(item, dict):
            continue
        widget_type = item.get("widget_type")
        if widget_type != NETWORK_STATUS_TOPOLOGY_CHART_TYPE:
            expanded.append(item)
            continue
        widget_id = item.get("widget_id")
        for ds_id in sorted(overlay_ids):
            key = (widget_id, ds_id)
            if key in seen:
                continue
            seen.add(key)
            expanded.append(
                {
                    "widget_id": widget_id,
                    "widget_type": widget_type,
                    "datasource_id": ds_id,
                }
            )
    return expanded

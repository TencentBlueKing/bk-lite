import pytest
from django.db import IntegrityError

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.network_status_topology_overlay import (
    NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS,
    collect_network_status_topology_overlay_datasource_ids,
    expand_widget_manifest_with_topology_overlay,
    view_sets_has_network_status_topology,
)

pytestmark = pytest.mark.django_db

CMDB_API, MONITOR_API = NETWORK_STATUS_TOPOLOGY_OVERLAY_REST_APIS


def _ds(rest_api, *, builtin=True, ds_id=None, name=None):
    kwargs = {
        "name": name or f"{rest_api}-{ds_id or 'auto'}",
        "rest_api": rest_api,
        "is_build_in": builtin,
        "created_by": "s",
        "updated_by": "s",
    }
    if ds_id is not None:
        kwargs["id"] = ds_id
        try:
            return DataSourceAPIModel.objects.create(**kwargs)
        except IntegrityError:
            kwargs.pop("id")
    return DataSourceAPIModel.objects.create(**kwargs)


def test_collect_overlay_ids_prefers_unique_builtin():
    cmdb = _ds(CMDB_API, ds_id=31)
    monitor = _ds(MONITOR_API, ds_id=32)
    _ds("other/query", ds_id=99)
    assert collect_network_status_topology_overlay_datasource_ids() == {cmdb.id, monitor.id}


def test_collect_overlay_ids_skips_ambiguous_unless_unique_builtin():
    _ds(CMDB_API, builtin=False, ds_id=31, name="cmdb-a")
    cmdb_b = _ds(CMDB_API, builtin=False, ds_id=41, name="cmdb-b")
    monitor = _ds(MONITOR_API, ds_id=32)
    assert collect_network_status_topology_overlay_datasource_ids() == {monitor.id}

    DataSourceAPIModel.objects.filter(id=cmdb_b.id).update(is_build_in=True)
    assert collect_network_status_topology_overlay_datasource_ids() == {monitor.id, cmdb_b.id}


def test_view_sets_detects_nested_dashboard_and_screen():
    dashboard = [{"itemType": "group", "subGridOpts": {"children": [{"valueConfig": {"chartType": "networkStatusTopology"}}]}}]
    screen = {"items": [{"valueConfig": {"chartType": "networkStatusTopology"}}]}
    scene = [{"valueConfig": {"sceneWidgetType": "networkStatusTopology"}}]
    assert view_sets_has_network_status_topology(dashboard) is True
    assert view_sets_has_network_status_topology(screen) is True
    assert view_sets_has_network_status_topology(scene) is True
    assert view_sets_has_network_status_topology([{"valueConfig": {"chartType": "line"}}]) is False


def test_expand_manifest_emits_two_rows_per_topology_widget():
    cmdb = _ds(CMDB_API, ds_id=31)
    monitor = _ds(MONITOR_API, ds_id=32)
    manifest = [
        {"widget_id": "topo-1", "widget_type": "networkStatusTopology", "datasource_id": None},
        {"widget_id": "line-1", "widget_type": "line", "datasource_id": 17},
    ]
    expanded = expand_widget_manifest_with_topology_overlay(manifest)
    topo_rows = [row for row in expanded if row["widget_id"] == "topo-1"]
    assert {row["datasource_id"] for row in topo_rows} == {cmdb.id, monitor.id}
    assert all(row["widget_type"] == "networkStatusTopology" for row in topo_rows)
    line_rows = [row for row in expanded if row["widget_id"] == "line-1"]
    assert line_rows == [{"widget_id": "line-1", "widget_type": "line", "datasource_id": 17}]


def test_canvas_data_source_ids_includes_overlay_without_explicit_datasource():
    from apps.operation_analysis.views.share_view import _canvas_data_source_ids

    cmdb = _ds(CMDB_API)
    monitor = _ds(MONITOR_API)
    view_sets = [{"valueConfig": {"chartType": "networkStatusTopology"}}]
    found = _canvas_data_source_ids(view_sets)
    assert {cmdb.id, monitor.id} <= found
    scene_sets = [{"valueConfig": {"sceneWidgetType": "networkStatusTopology"}}]
    assert {cmdb.id, monitor.id} <= _canvas_data_source_ids(scene_sets)


def test_canvas_data_source_ids_excludes_overlay_without_topology_widget():
    from apps.operation_analysis.views.share_view import _canvas_data_source_ids

    cmdb = _ds(CMDB_API)
    monitor = _ds(MONITOR_API)
    view_sets = [{"valueConfig": {"chartType": "line", "dataSource": 99}}]
    found = _canvas_data_source_ids(view_sets)
    assert found == {99}
    assert found.isdisjoint({cmdb.id, monitor.id})

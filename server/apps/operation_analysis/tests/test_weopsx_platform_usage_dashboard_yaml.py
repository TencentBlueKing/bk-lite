"""WeOpsX 平台使用仪表盘 YAML：随 init_builtin_canvases 进入内置目录。"""

from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import (
    WEOPSX_PLATFORM_USAGE_YAML_PATH,
    YAML_FILE_PATH,
    _get_builtin_canvas_file_paths,
)
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "weopsx_platform_usage_dashboard.yaml"
BUILTIN_PATH = SUPPORT_DIR / "builtin_canvases.yaml"

TIME_BOUND_WIDGET_IDS = {
    "weopsx-mon-most-alerts",
    "weopsx-mon-least-alerts",
    "weopsx-log-policy-top",
    "weopsx-alert-loop",
    "weopsx-alert-source-top",
    "weopsx-alert-rule-top",
    "weopsx-job-success",
}

REUSED_DATASOURCE_APIS = {
    "cmdb/get_cmdb_statistics",
    "cmdb/get_cmdb_model_instance_top",
    "monitor/get_monitor_statistics",
    "alert/get_alert_snapshot_statistics",
    "alert/get_alert_source_statistics",
    "alert/get_alert_period_statistics",
    "alert/get_alert_source_event_top",
}


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def _iter_widgets(view_sets):
    for item in view_sets:
        if item.get("itemType") == "group":
            yield from (item.get("subGridOpts") or {}).get("children") or []
        else:
            yield item


def test_weopsx_yaml_is_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(YAML_FILE_PATH).resolve() != SAMPLE_PATH.resolve()
    assert Path(WEOPSX_PLATFORM_USAGE_YAML_PATH).resolve() == SAMPLE_PATH.resolve()
    loaded = {Path(path).resolve() for path in _get_builtin_canvas_file_paths()}
    assert SAMPLE_PATH.resolve() in loaded
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("dashboards") or []}
    assert "dashboard::WeOpsX平台使用_内置" not in builtin_keys


def test_weopsx_yaml_parses_and_binds_organization_and_time():
    payload = _load_sample()
    document = YAMLDocument(**payload)

    dashboard = document.dashboards[0]
    assert dashboard.name == "WeOpsX 平台使用"
    assert dashboard.key == "dashboard::WeOpsX平台使用_内置"
    filters = {item["key"]: item for item in dashboard.filters}
    assert set(filters) == {"organization", "time"}
    assert filters["organization"]["type"] == "string"
    assert (filters["organization"].get("inputConfig") or {}).get("control") == "organization"
    assert "inputMode" not in filters["organization"]
    assert "defaultValue" not in filters["organization"] or filters["organization"].get("defaultValue") in (None, "", {})
    assert filters["time"]["type"] == "timeRange"
    assert filters["time"]["defaultValue"]["selectValue"] == 10080

    widgets = list(_iter_widgets(dashboard.view_sets))
    assert widgets
    for widget in widgets:
        value_config = widget["valueConfig"]
        assert value_config.get("dataSource"), widget["id"]
        assert value_config["filterBindings"]["organization__string"] is True
        bound_time = value_config["filterBindings"].get("time__timeRange") is True
        assert bound_time == (widget["id"] in TIME_BOUND_WIDGET_IDS), widget["id"]
        org_param = next(param for param in value_config["dataSourceParams"] if param["name"] == "organization")
        assert org_param["filterType"] == "filter"
        assert (org_param.get("inputConfig") or {}).get("control") == "organization"
        assert "inputMode" not in org_param

    referenced = set(dashboard.refs.datasource_keys)
    configured = {widget["valueConfig"]["dataSource"] for widget in widgets}
    assert configured <= referenced
    selected = {widget["id"]: widget["valueConfig"].get("selectedFields") for widget in widgets if widget["valueConfig"].get("chartType") == "single"}
    assert selected["weopsx-mon-objects"] == ["monitor_object_total"]
    assert selected["weopsx-mon-instances"] == ["monitor_instance_total"]
    assert selected["weopsx-mon-metrics"] == ["metric_total"]
    assert selected["weopsx-mon-policies"] == ["policy_total"]
    assert selected["weopsx-cmdb-classifications"] == ["classification_count"]
    assert selected["weopsx-cmdb-models"] == ["model_count"]
    assert selected["weopsx-cmdb-instances"] == ["instance_count"]
    assert selected["weopsx-kpi-nodes"] == ["node_total"]
    assert selected["weopsx-node-total"] == ["node_total"]
    assert selected["weopsx-node-collectors"] == ["collector_total"]
    assert selected["weopsx-node-clouds"] == ["cloud_region_total"]
    widget_ids = {widget["id"] for widget in widgets}
    assert "weopsx-cmdb-collected" not in widget_ids
    assert "weopsx-cmdb-model-top" not in widget_ids
    assert "weopsx-cmdb-class-top" in widget_ids
    assert "weopsx-cmdb-coverage" in widget_ids
    cmdb_group = next(item for item in dashboard.view_sets if item["id"] == "group-cmdb")
    assert [(c["id"], c["x"], c["w"]) for c in cmdb_group["subGridOpts"]["children"]] == [
        ("weopsx-cmdb-classifications", 0, 2),
        ("weopsx-cmdb-models", 2, 2),
        ("weopsx-cmdb-instances", 4, 2),
        ("weopsx-cmdb-coverage", 6, 2),
        ("weopsx-cmdb-class-top", 8, 4),
    ]
    alert_group = next(item for item in dashboard.view_sets if item["id"] == "group-alert")
    assert [(c["id"], c["x"], c["y"], c["w"]) for c in alert_group["subGridOpts"]["children"]] == [
        ("weopsx-alert-active", 0, 0, 4),
        ("weopsx-alert-sources", 4, 0, 4),
        ("weopsx-alert-loop", 8, 0, 4),
        ("weopsx-alert-source-top", 0, 5, 6),
        ("weopsx-alert-rule-top", 6, 5, 6),
    ]
    loop = next(widget for widget in widgets if widget["id"] == "weopsx-alert-loop")
    assert loop["valueConfig"]["gaugeMax"] == 200
    channel = next(widget for widget in widgets if widget["id"] == "weopsx-sys-enabled")
    assert "已配置即视为已启用" in channel["description"]
    for datasource in document.datasources:
        org_param = next(param for param in datasource.params if param["name"] == "organization")
        assert org_param["filterType"] == "filter"
        assert (org_param.get("inputConfig") or {}).get("control") == "organization"
        assert "inputMode" not in org_param


def test_reused_datasources_declare_organization_parameter():
    payload = yaml.safe_load(BUILTIN_PATH.read_text(encoding="utf-8"))
    by_api = {item["rest_api"]: item for item in payload["datasources"]}
    for rest_api in REUSED_DATASOURCE_APIS:
        params = by_api[rest_api]["params"]
        org_param = next(param for param in params if param["name"] == "organization")
        assert org_param["type"] == "string"
        assert org_param["value"] == ""
        assert org_param["filterType"] == "filter"
        assert (org_param.get("inputConfig") or {}).get("control") == "organization"
        assert "inputMode" not in org_param
    assert next(param["value"] for param in by_api["cmdb/get_cmdb_model_instance_top"]["params"] if param["name"] == "group_by") == "model"
    assert next(param["alias_name"] for param in by_api["cmdb/get_cmdb_model_instance_top"]["params"] if param["name"] == "group_by") == "排行维度"
    assert by_api["cmdb/get_cmdb_model_instance_top"]["name"] == "CMDB 实例排行（按模型/分类）"
    period_fields = {field["key"] for field in by_api["alert/get_alert_period_statistics"]["field_schema"]}
    assert {"closed_alert_count", "closed_loop_rate"} <= period_fields
    cmdb_fields = {field["key"] for field in by_api["cmdb/get_cmdb_statistics"]["field_schema"]}
    assert {"collected_instance_count", "collect_coverage_rate"} <= cmdb_fields
    org_widget = next(widget for widget in _iter_widgets(_load_sample()["dashboards"][0]["view_sets"]) if widget["id"] == "weopsx-sys-orgs")
    assert "下级" in org_widget["description"]


def test_weopsx_dashboard_survives_builtin_merge():
    from apps.operation_analysis.management.commands.init_builtin_canvases import (
        _get_builtin_canvas_file_paths,
        _load_source_api_document,
        _merge_yaml_documents,
    )

    documents = [_load_source_api_document()]
    for file_path in _get_builtin_canvas_file_paths():
        documents.append(yaml.safe_load(Path(file_path).read_text(encoding="utf-8")))
    merged = _merge_yaml_documents(documents)
    document = YAMLDocument(**merged)
    keys = {item.key for item in document.dashboards}
    assert "dashboard::WeOpsX平台使用_内置" in keys
    dashboard = next(item for item in document.dashboards if item.key == "dashboard::WeOpsX平台使用_内置")
    available = {item.key for item in document.datasources}
    assert set(dashboard.refs.datasource_keys) <= available
    widgets = list(_iter_widgets(dashboard.view_sets))
    assert {widget["valueConfig"]["dataSource"] for widget in widgets} <= available

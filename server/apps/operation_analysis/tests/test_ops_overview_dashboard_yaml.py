"""运维总览内置画布：复用已有数据源，组织筛选与时间后缀跟其他 WeOpsX 画布一致。"""

import base64
import hashlib
import json
import struct
from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import (
    WEOPSX_OPS_OVERVIEW_YAML_PATH,
    YAML_FILE_PATH,
    _get_builtin_canvas_file_paths,
)
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "weopsx_ops_overview_dashboard.yaml"

TIME_BOUND_WIDGET_IDS = {
    "ops-alert-trend",
}
TIME_SUFFIX_WIDGET_IDS = {"ops-alert-trend"}


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def _iter_widgets(view_sets):
    for item in view_sets:
        if item.get("itemType") == "group":
            yield from (item.get("subGridOpts") or {}).get("children") or []
        else:
            yield item


def test_ops_overview_yaml_is_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(WEOPSX_OPS_OVERVIEW_YAML_PATH).resolve() == SAMPLE_PATH.resolve()
    loaded = {Path(path).resolve() for path in _get_builtin_canvas_file_paths()}
    assert SAMPLE_PATH.resolve() in loaded
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("dashboards") or []}
    assert "dashboard::运维总览_内置" not in builtin_keys


def test_ops_overview_yaml_binds_organization_time_and_reusable_widgets():
    document = YAMLDocument(**_load_sample())
    dashboard = document.dashboards[0]
    assert dashboard.name == "运维总览"
    assert dashboard.key == "dashboard::运维总览_内置"
    assert dashboard.other.get("gridCols") == 24
    assert dashboard.other.get("gridRowHeight") == 30
    groups = {item["id"]: item for item in dashboard.view_sets}
    assert [
        (groups[key]["x"], groups[key]["y"], groups[key]["w"], groups[key]["h"])
        for key in (
            "group-kpi",
            "group-resource",
            "group-monitor",
            "group-alert",
        )
    ] == [
        (0, 0, 24, 7),
        (0, 7, 24, 10),
        (0, 17, 24, 10),
        (0, 27, 24, 10),
    ]
    filters = {item["key"]: item for item in dashboard.filters}
    assert set(filters) == {"organization", "time"}
    assert (filters["organization"].get("inputConfig") or {}).get("control") == "organization"
    assert filters["time"]["defaultValue"]["selectValue"] == 10080

    widgets = list(_iter_widgets(dashboard.view_sets))
    widget_ids = {widget["id"] for widget in widgets}
    assert widget_ids >= TIME_BOUND_WIDGET_IDS | {
        "ops-kpi-resources",
        "ops-kpi-nodes",
        "ops-kpi-severe",
        "ops-app-top",
        "ops-resource-types",
        "ops-monitor-ring",
    }
    assert {
        "ops-app-total",
        "ops-app-with-alert",
        "ops-app-without-alert",
    }.isdisjoint(widget_ids)
    assert "ops-app-ring" not in widget_ids
    assert "ops-collect-ring" not in widget_ids
    assert "ops-resource-total" not in widget_ids
    assert "ops-collect-configured" not in widget_ids
    assert "ops-collect-missing" not in widget_ids
    overview_text = SAMPLE_PATH.read_text(encoding="utf-8")
    assert "uncollected_instance_count" not in overview_text
    assert "collected_instance_share" not in overview_text
    assert "uncollected_instance_share" not in overview_text
    for widget in widgets:
        value_config = widget["valueConfig"]
        assert value_config["filterBindings"]["organization__string"] is True
        bound_time = value_config["filterBindings"].get("time__timeRange") is True
        assert bound_time == (widget["id"] in TIME_BOUND_WIDGET_IDS)
        if widget["id"] in TIME_SUFFIX_WIDGET_IDS:
            assert widget["name"].endswith("（$time$）")
        else:
            assert not str(widget["name"]).endswith("（$time$）")
        org_param = next(param for param in value_config["dataSourceParams"] if param["name"] == "organization")
        assert (org_param.get("inputConfig") or {}).get("control") == "organization"

    by_id = {widget["id"]: widget for widget in widgets}
    assert by_id["ops-kpi-severe"]["valueConfig"]["selectedFields"] == ["severe_active_count"]
    upload_icon_lengths = {
        "ops-kpi-resources": 10026,
        "ops-kpi-monitor": 5946,
        "ops-kpi-open-alerts": 28558,
        "ops-kpi-severe": 24818,
    }
    for widget_id, icon_length in upload_icon_lengths.items():
        style = by_id[widget_id]["valueConfig"]["singleStyle"]
        assert style["showIcon"] is True
        assert style["iconSource"] == "upload"
        assert style.get("iconSize") == "medium"
        assert "iconKey" not in style
        assert style["iconImage"].startswith("data:image/png;base64,")
        assert len(style["iconImage"]) == icon_length
    node = by_id["ops-kpi-nodes"]
    assert node["name"] == "告警应用数"
    assert "description" not in node
    assert (node["x"], node["y"], node["w"], node["h"]) == (10, 0, 4, 5)
    assert node["valueConfig"]["dataSource"] == "关联告警汇总::monitor/get_cmdb_relation_alert_aggregation"
    assert node["valueConfig"]["selectedFields"] == ["with_alert_count"]
    assert set(node["valueConfig"]["singleStyle"]) == {"showIcon", "iconSource", "iconImage"}
    assert node["valueConfig"]["singleStyle"]["showIcon"] is True
    assert node["valueConfig"]["singleStyle"]["iconSource"] == "upload"
    assert node["valueConfig"]["interaction"] == {
        "kind": "title",
        "name": "查看应用",
        "url": "/cmdb/views/application",
        "openMode": "newTab",
    }
    node_view = next(param for param in node["valueConfig"]["dataSourceParams"] if param["name"] == "view")
    assert node_view["value"] == "summary"
    assert node_view["filterType"] == "fixed"
    assert [item["color"] for item in node["valueConfig"]["thresholdColors"]] == ["#366ce4", "#366ce4", "#366ce4"]
    assert by_id["ops-kpi-resources"]["valueConfig"]["selectedFields"] == ["instance_count"]
    assert [
        (by_id[widget_id]["x"], by_id[widget_id]["w"], by_id[widget_id]["h"])
        for widget_id in (
            "ops-kpi-resources",
            "ops-kpi-monitor",
            "ops-kpi-nodes",
            "ops-kpi-open-alerts",
            "ops-kpi-severe",
        )
    ] == [(0, 5, 5), (5, 5, 5), (10, 4, 5), (14, 5, 5), (19, 5, 5)]
    assert (by_id["ops-resource-types"]["x"], by_id["ops-resource-types"]["w"], by_id["ops-resource-types"]["h"]) == (12, 12, 8)
    assert (by_id["ops-app-top"]["x"], by_id["ops-app-top"]["w"], by_id["ops-app-top"]["h"]) == (0, 12, 8)
    assert by_id["ops-monitor-ring"]["valueConfig"]["pieScalarFields"][0]["field"] == "monitor_instance_active"
    assert "ops-gauge-cpu" not in by_id
    assert "ops-gauge-memory" not in by_id
    assert "ops-gauge-disk" not in by_id
    host_metrics = by_id["ops-host-key-metrics"]
    assert host_metrics["name"] == "主机关键指标"
    assert "description" not in host_metrics
    assert (host_metrics["x"], host_metrics["y"], host_metrics["w"], host_metrics["h"]) == (10, 0, 8, 8)
    assert host_metrics["valueConfig"]["chartType"] == "topN"
    assert host_metrics["valueConfig"]["dataSource"] == "主机资源使用率Top10::monitor/get_host_resource_top"
    assert "barMode" not in host_metrics["valueConfig"]
    assert "topNScalarFields" not in host_metrics["valueConfig"]
    assert host_metrics["valueConfig"]["unitId"] == "percent"
    assert host_metrics["valueConfig"]["topNLabelField"] == "display_name"
    assert host_metrics["valueConfig"]["topNValueField"] == "usage_percent"
    assert host_metrics["valueConfig"].get("compare") is not True
    assert host_metrics["valueConfig"]["interaction"]["url"] == "/monitor/view/dashboard/host"
    metric_type = next(param for param in host_metrics["valueConfig"]["dataSourceParams"] if param["name"] == "metric_type")
    assert metric_type["value"] == "cpu"
    assert metric_type["inputConfig"]["control"] == "radio"
    assert metric_type["inputConfig"]["componentSwitch"] is True
    assert {item["value"] for item in metric_type["inputConfig"]["optionsSource"]["staticItems"]} == {"cpu", "memory", "disk"}
    assert host_metrics["valueConfig"]["filterBindings"]["instance_ids__string"] is False
    assert host_metrics["valueConfig"]["filterBindings"]["organization__string"] is True
    assert [param["type"] for param in host_metrics["valueConfig"]["dataSourceParams"] if param["type"] in {"timeRange", "dateRange"}] == []
    assert "time__timeRange" not in host_metrics["valueConfig"]["filterBindings"]
    trend = by_id["ops-alert-trend"]["valueConfig"]
    assert trend["dataSource"] == "告警新增与关闭趋势::alert/get_alert_open_close_trend"
    trend_params = {param["name"]: param["value"] for param in trend["dataSourceParams"]}
    assert set(trend_params) == {"time", "organization"}
    assert trend_params["time"] == 10080
    assert by_id["ops-resource-types"]["valueConfig"]["chartType"] == "topN"
    assert by_id["ops-resource-types"]["valueConfig"]["topNLabelField"] == "classification_name"
    assert by_id["ops-resource-types"]["valueConfig"]["topNValueField"] == "value"
    assert by_id["ops-resource-types"]["valueConfig"]["interaction"]["name"] == "查看全部"
    assert by_id["ops-monitor-ring"]["name"] == "监控接入概况"
    assert by_id["ops-host-key-metrics"]["name"] == "主机关键指标"
    assert "barMode" not in by_id["ops-resource-types"]["valueConfig"]
    assert by_id["ops-app-top"]["valueConfig"]["chartType"] == "table"
    assert [column["key"] for column in by_id["ops-app-top"]["valueConfig"]["tableConfig"]["columns"]] == [
        "name",
        "alert_count",
        "share",
    ]
    monitor_alerts = by_id["ops-monitor-alerts"]
    assert monitor_alerts["valueConfig"]["dataSource"] == "监控异常严重度TOP5::monitor/query_latest_active_alerts"
    assert "description" not in monitor_alerts
    monitor_order = {param["name"]: param for param in monitor_alerts["valueConfig"]["dataSourceParams"]}
    assert monitor_order["order"]["value"] == "severity"
    assert monitor_order["order"]["filterType"] == "fixed"
    assert monitor_order["limit"]["value"] == 5
    assert monitor_order["limit"]["filterType"] == "fixed"
    monitor_columns = monitor_alerts["valueConfig"]["tableConfig"]["columns"]
    assert [column["key"] for column in monitor_columns] == [
        "monitor_instance_name",
        "metric_name",
        "value",
        "duration_text",
        "level",
    ]
    assert monitor_columns[2]["title"] == "告警记录值"
    assert monitor_columns[3]["title"] == "持续时长"
    assert monitor_columns[4]["title"] == "告警等级"
    assert "cellType" not in monitor_columns[4]
    assert any(item["value"] == "critical" and item["result"]["text"] == "严重" for item in monitor_columns[4]["valueMappings"])
    assert any(item["value"] == "warning" and item["result"]["color"] == "#FFAD42" for item in monitor_columns[4]["valueMappings"])
    alert_columns = by_id["ops-alert-top"]["valueConfig"]["tableConfig"]["columns"]
    assert [column["key"] for column in alert_columns] == [
        "resource_name",
        "title",
        "level",
        "created_at",
    ]
    assert "cellType" not in alert_columns[2]
    assert any(item["value"] == "严重" and item["result"]["color"] == "#F43B2C" for item in alert_columns[2]["valueMappings"])
    assert by_id["ops-kpi-resources"]["valueConfig"]["interaction"]["url"] == "/cmdb/assetOverview"
    assert by_id["ops-app-top"]["valueConfig"]["interaction"]["name"] == "查看全部"
    assert "节点用法总览::node/get_node_usage_statistics" not in dashboard.refs.datasource_keys
    assert "主机资源快照::monitor/get_host_resource_snapshot" not in dashboard.refs.datasource_keys
    assert "监控活跃告警::monitor/query_latest_active_alerts" not in dashboard.refs.datasource_keys
    assert {widget["valueConfig"]["dataSource"] for widget in widgets} <= set(dashboard.refs.datasource_keys)


def test_ops_overview_survives_builtin_merge():
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
    dashboard = next(item for item in document.dashboards if item.key == "dashboard::运维总览_内置")
    available = {item.key for item in document.datasources}
    assert set(dashboard.refs.datasource_keys) <= available
    relation_keys = {item.key for item in document.datasources if item.rest_api == "monitor/get_cmdb_relation_alert_aggregation"}
    assert relation_keys == {
        "关联告警汇总::monitor/get_cmdb_relation_alert_aggregation",
        "关联告警 TOP::monitor/get_cmdb_relation_alert_aggregation",
    }
    by_key = {item.key: item for item in document.datasources}

    def field_keys(datasource_key):
        return {field["key"] for field in by_key[datasource_key].field_schema}

    assert {"with_alert_share", "without_alert_share"} <= field_keys("关联告警汇总::monitor/get_cmdb_relation_alert_aggregation")
    assert "share" in field_keys("关联告警 TOP::monitor/get_cmdb_relation_alert_aggregation")
    cmdb_fields = field_keys("模型/实例/分类总数统计::cmdb/get_cmdb_statistics")
    assert {"collected_instance_count", "collect_coverage_rate", "instance_count"} <= cmdb_fields
    assert "uncollected_instance_count" not in cmdb_fields
    assert "collected_instance_share" not in cmdb_fields
    assert "uncollected_instance_share" not in cmdb_fields
    assert {"value", "metric_name"} <= field_keys("监控活跃告警::monitor/query_latest_active_alerts")
    latest = by_key["监控活跃告警::monitor/query_latest_active_alerts"]
    assert "order" not in {param["name"] for param in latest.params}
    assert next(param for param in latest.params if param["name"] == "limit")["value"] == 10
    severity = by_key["监控异常严重度TOP5::monitor/query_latest_active_alerts"]
    assert severity.rest_api == "monitor/query_latest_active_alerts"
    severity_params = {param["name"]: param for param in severity.params}
    assert severity_params["order"]["value"] == "severity"
    assert severity_params["order"]["filterType"] == "fixed"
    assert severity_params["limit"]["value"] == 5
    assert "duration_text" in field_keys("监控异常严重度TOP5::monitor/query_latest_active_alerts")
    host_top = by_key["主机资源使用率Top10::monitor/get_host_resource_top"]
    host_org = next(param for param in host_top.params if param["name"] == "organization")
    assert host_org["value"] in ("", None)
    assert host_org["filterType"] == "filter"
    assert (host_org.get("inputConfig") or {}).get("control") == "organization"


OVERVIEW_NODE_IDS = (
    "group-kpi",
    "ops-kpi-resources",
    "ops-kpi-monitor",
    "ops-kpi-nodes",
    "ops-kpi-open-alerts",
    "ops-kpi-severe",
    "group-resource",
    "ops-app-top",
    "ops-resource-types",
    "group-monitor",
    "ops-monitor-alerts",
    "ops-host-key-metrics",
    "ops-monitor-ring",
    "group-alert",
    "ops-alert-top",
    "ops-alert-trend",
    "ops-alert-level",
)


def _iter_nodes(view_sets):
    for item in view_sets:
        yield item
        if item.get("itemType") == "group":
            yield from _iter_nodes((item.get("subGridOpts") or {}).get("children") or [])


def _description_paths(value, path=""):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            next_path = f"{path}.{key}" if path else key
            if key in {"description", "desc"}:
                found.append((next_path, child))
            found.extend(_description_paths(child, next_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_description_paths(child, f"{path}[{index}]"))
    return found
KPI_ROW_ORDER = (
    "ops-kpi-resources",
    "ops-kpi-monitor",
    "ops-kpi-nodes",
    "ops-kpi-open-alerts",
    "ops-kpi-severe",
)
KPI_ROW_BOXES = {
    "ops-kpi-resources": (0, 0, 5, 5),
    "ops-kpi-monitor": (5, 0, 5, 5),
    "ops-kpi-nodes": (10, 0, 4, 5),
    "ops-kpi-open-alerts": (14, 0, 5, 5),
    "ops-kpi-severe": (19, 0, 5, 5),
}
KPI_EXCEPT_X_SHA256 = {
    "ops-kpi-resources": "804e7a1e344d7203d9a60e3d119eb570a7bac88bda0738b633c891b036c7dc64",
    "ops-kpi-monitor": "588a5d6a057a24e343c02c2487e7364a74975cfd0045396a500e5c340965467e",
    "ops-kpi-nodes": "4cc2216e150f4c92e184b46158e8e1c995a9d6cf7669903ca4fa64d5409360f9",
    "ops-kpi-open-alerts": "e9d9c107f376e06c6ccd826f73c4851811f3874c53995db0423ebba79152a823",
    "ops-kpi-severe": "81a159c901d335c4672c5e8b40d6fa4c277e05b1ab2da1ef5d5081937cda50ab",
}
UNCHANGED_WIDGET_SHA256 = {
    "ops-app-top": "c14407cfd6aa1708b81f06661d65b88867d7043a69799b9170f883e7fe8fc759",
    "ops-resource-types": "74fbcca1952c1fbac557218633b76252c3e64a85b6ad6952ed015fb3d6a13b63",
    "ops-monitor-ring": "115e3af3106c294fcd068803623319131a25a5ff699f95701f2caa43d04fddb4",
    "ops-alert-trend": "f38d458fc1fc1f6aa5e54b5f2b77b4cc24fcd0eadef4ce7d8dad2650820e22fd",
    "ops-alert-level": "7e56f6c0990b344d992983319a05470a992f18c805a8ea709b2421287c964ab1",
}
DASHBOARD_META_SHA256 = "eb851050246b16a7dcf4ce7f0450b25ec87e853c757156762b7a22ddf0b88ff7"
MONITOR_ALERTS_VALUE_CONFIG_SHA256 = "0df97225f57605c3c07c5353f5b8035134afef10447a53f2b01fccd33c366396"
ALERT_TOP_VALUE_CONFIG_SHA256 = "1725b5f04fe56eaee9e4db26507b34f1bce440b86974e607388eb0ded197a528"


def _canonical_sha256(value):
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _language_widgets(filename):
    catalog = yaml.safe_load((SUPPORT_DIR.parent / "language" / filename).read_text(encoding="utf-8"))
    return catalog["dashboards"]["dashboard::运维总览_内置"]["widgets"]


def test_ops_overview_syncs_dashboard80_display_without_touching_other_widgets():
    sample = _load_sample()
    dashboard = sample["dashboards"][0]
    meta = {key: value for key, value in dashboard.items() if key != "view_sets"}
    assert _canonical_sha256(meta) == DASHBOARD_META_SHA256
    assert [item["key"] for item in dashboard["filters"]] == ["organization", "time"]

    widgets = list(_iter_widgets(dashboard["view_sets"]))
    by_id = {widget["id"]: widget for widget in widgets}
    assert len(widgets) == 13
    assert set(UNCHANGED_WIDGET_SHA256) | set(KPI_ROW_ORDER) | {
        "ops-host-key-metrics",
        "ops-monitor-alerts",
        "ops-alert-top",
    } == set(by_id)
    for widget_id, digest in UNCHANGED_WIDGET_SHA256.items():
        assert _canonical_sha256(by_id[widget_id]) == digest

    nodes = list(_iter_nodes(dashboard["view_sets"]))
    assert [item["id"] for item in nodes] == list(OVERVIEW_NODE_IDS)
    for item in nodes:
        assert _description_paths(item) == []

    node = by_id["ops-kpi-nodes"]
    style = node["valueConfig"]["singleStyle"]
    assert style == {
        "showIcon": True,
        "iconSource": "upload",
        **{"iconImage": style["iconImage"]},
    }
    prefix = "data:image/png;base64,"
    assert style["iconImage"].startswith(prefix)
    raw = base64.b64decode(style["iconImage"][len(prefix):], validate=True)
    assert len(raw) == 7375
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
    assert raw[12:16] == b"IHDR"
    assert (width, height, bit_depth, color_type) == (256, 256, 8, 6)
    assert node["valueConfig"]["dataSource"] == "关联告警汇总::monitor/get_cmdb_relation_alert_aggregation"

    host = by_id["ops-host-key-metrics"]
    assert host["valueConfig"]["dataSource"] == "主机资源使用率Top10::monitor/get_host_resource_top"
    assert host["valueConfig"]["filterBindings"] == {
        "instance_ids__string": False,
        "organization__string": True,
    }
    params = {param["name"]: param for param in host["valueConfig"]["dataSourceParams"]}
    assert list(params) == ["metric_type", "instance_ids", "organization"]
    assert params["metric_type"]["inputConfig"]["control"] == "radio"
    assert params["metric_type"]["filterType"] == "params"
    instance_ids = params["instance_ids"]
    assert instance_ids["filterType"] == "filter"
    assert instance_ids["alias_name"] == "主机"
    assert instance_ids["value"] is None
    source_ref = instance_ids["inputConfig"]["optionsSource"]["sourceRef"]
    assert source_ref == {"type": "rest_api", "value": "monitor/get_host_instance_list"}
    assert "id" not in source_ref
    assert not str(source_ref["value"]).isdigit()

    monitor = by_id["ops-monitor-alerts"]
    assert _canonical_sha256(monitor["valueConfig"]) == MONITOR_ALERTS_VALUE_CONFIG_SHA256
    assert monitor["valueConfig"]["dataSource"] == "监控异常严重度TOP5::monitor/query_latest_active_alerts"

    alert = by_id["ops-alert-top"]
    assert _canonical_sha256(alert["valueConfig"]) == ALERT_TOP_VALUE_CONFIG_SHA256
    level = next(column for column in alert["valueConfig"]["tableConfig"]["columns"] if column["key"] == "level")
    assert "cellType" not in level
    assert any(item["result"]["color"] == "#F43B2C" and item["result"]["text"] == "严重" for item in level["valueMappings"])

    for filename in ("zh-Hans.yaml", "en.yaml"):
        catalog = yaml.safe_load((SUPPORT_DIR.parent / "language" / filename).read_text(encoding="utf-8"))
        entry = catalog["dashboards"]["dashboard::运维总览_内置"]
        assert isinstance(entry["desc"], str) and entry["desc"].strip()
        entries = entry["widgets"]
        assert set(entries) == set(OVERVIEW_NODE_IDS)
        for widget_id in OVERVIEW_NODE_IDS:
            assert "description" not in entries[widget_id]
            assert "desc" not in entries[widget_id]
        assert entries["ops-host-key-metrics"]["params"]["instance_ids"] in {"主机", "Host"}

    from apps.core.utils.loader import clear_language_cache
    from apps.operation_analysis.services.builtin_i18n import overlay_canvas_payload

    clear_language_cache("operation_analysis")

    class _Builtin:
        is_build_in = True
        build_in_key = "dashboard::运维总览_内置"

    for language in ("zh-Hans", "en"):
        overlaid = overlay_canvas_payload(
            {"name": dashboard["name"], "desc": dashboard["desc"], "view_sets": dashboard["view_sets"]},
            _Builtin(),
            language,
        )
        assert isinstance(overlaid["desc"], str) and overlaid["desc"].strip()
        overlaid_by_id = {item["id"]: item for item in _iter_nodes(overlaid["view_sets"])}
        for item in overlaid_by_id.values():
            assert _description_paths(item) == []
        assert overlaid_by_id["ops-host-key-metrics"]["valueConfig"]["filterBindings"]["instance_ids__string"] is False
        assert overlaid_by_id["ops-kpi-nodes"]["valueConfig"]["singleStyle"]["iconImage"].startswith("data:image/png;base64,")
        stored_null = {
            "name": "告警应用数",
            "description": None,
            "valueConfig": {"description": None},
        }
        injected = overlay_canvas_payload(
            {"name": dashboard["name"], "view_sets": [stored_null | {"id": "ops-kpi-nodes"}]},
            _Builtin(),
            language,
        )
        node = injected["view_sets"][0]
        assert "description" not in node or node["description"] in (None, "")
        assert node["valueConfig"].get("description") in (None, "")


def test_ops_overview_kpi_row_places_alerted_applications_after_monitor_instances():
    dashboard = _load_sample()["dashboards"][0]
    group = next(item for item in dashboard["view_sets"] if item["id"] == "group-kpi")
    children = group["subGridOpts"]["children"]
    assert [item["id"] for item in children] == list(KPI_ROW_ORDER)
    assert (group["x"], group["y"], group["w"], group["h"]) == (0, 0, 24, 7)

    occupied = []
    for item in children:
        assert (item["x"], item["y"], item["w"], item["h"]) == KPI_ROW_BOXES[item["id"]]
        assert "description" not in item
        body = {key: value for key, value in item.items() if key != "x"}
        assert _canonical_sha256(body) == KPI_EXCEPT_X_SHA256[item["id"]]
        occupied.append((item["x"], item["x"] + item["w"]))
    occupied.sort()
    assert occupied[0][0] == 0
    assert occupied[-1][1] == group["w"]
    for (start, end), (next_start, _) in zip(occupied, occupied[1:]):
        assert end == next_start

    others = [item for item in _iter_widgets(dashboard["view_sets"]) if item["id"] not in KPI_ROW_ORDER]
    assert {item["id"] for item in others} == set(UNCHANGED_WIDGET_SHA256) | {
        "ops-host-key-metrics",
        "ops-monitor-alerts",
        "ops-alert-top",
    }
    for widget_id, digest in UNCHANGED_WIDGET_SHA256.items():
        widget = next(item for item in others if item["id"] == widget_id)
        assert _canonical_sha256(widget) == digest

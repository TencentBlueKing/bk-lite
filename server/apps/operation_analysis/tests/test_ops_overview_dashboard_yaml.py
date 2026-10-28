"""运维总览内置画布：复用已有数据源，组织筛选与时间后缀跟其他 WeOpsX 画布一致。"""

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
    "ops-host-key-metrics",
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
        "ops-app-total",
        "ops-app-with-alert",
        "ops-app-without-alert",
        "ops-monitor-ring",
    }
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
    assert node["name"] == "节点"
    assert (node["x"], node["y"], node["w"], node["h"]) == (20, 0, 4, 5)
    assert node["valueConfig"]["dataSource"] == "节点用法总览::node/get_node_usage_statistics"
    assert node["valueConfig"]["selectedFields"] == ["node_total"]
    assert node["valueConfig"]["singleStyle"] == {
        "showIcon": True,
        "iconSource": "builtin",
        "iconKey": "icons/mm-node_Node",
        "iconSize": "medium",
    }
    assert node["valueConfig"]["interaction"] == {
        "kind": "title",
        "name": "节点管理",
        "url": "/node-manager/cloudregion",
        "openMode": "newTab",
    }
    assert [item["color"] for item in node["valueConfig"]["thresholdColors"]] == ["#366ce4", "#366ce4", "#366ce4"]
    assert by_id["ops-kpi-resources"]["valueConfig"]["selectedFields"] == ["instance_count"]
    assert [
        (by_id[widget_id]["x"], by_id[widget_id]["w"], by_id[widget_id]["h"])
        for widget_id in (
            "ops-kpi-resources",
            "ops-kpi-monitor",
            "ops-kpi-open-alerts",
            "ops-kpi-severe",
        )
    ] == [(0, 5, 5), (5, 5, 5), (10, 5, 5), (15, 5, 5)]
    assert by_id["ops-app-total"]["valueConfig"]["chartType"] == "single"
    assert by_id["ops-app-total"]["valueConfig"]["dataSource"] == "关联告警汇总::monitor/get_cmdb_relation_alert_aggregation"
    assert by_id["ops-app-total"]["valueConfig"]["selectedFields"] == ["total_count"]
    assert by_id["ops-app-with-alert"]["valueConfig"]["descriptionField"] == "with_alert_share"
    assert by_id["ops-app-with-alert"]["valueConfig"]["selectedFields"] == ["with_alert_count"]
    assert by_id["ops-app-without-alert"]["valueConfig"]["descriptionField"] == "without_alert_share"
    assert by_id["ops-app-without-alert"]["valueConfig"]["selectedFields"] == ["without_alert_count"]
    assert (by_id["ops-resource-types"]["x"], by_id["ops-resource-types"]["w"], by_id["ops-resource-types"]["h"]) == (9, 7, 8)
    assert (by_id["ops-app-total"]["x"], by_id["ops-app-total"]["w"], by_id["ops-app-total"]["h"]) == (16, 4, 8)
    assert (by_id["ops-app-with-alert"]["x"], by_id["ops-app-with-alert"]["y"], by_id["ops-app-with-alert"]["w"]) == (20, 0, 4)
    assert (by_id["ops-app-without-alert"]["x"], by_id["ops-app-without-alert"]["y"]) == (20, 4)
    assert (by_id["ops-app-top"]["x"], by_id["ops-app-top"]["w"], by_id["ops-app-top"]["h"]) == (0, 9, 8)
    assert by_id["ops-monitor-ring"]["valueConfig"]["pieScalarFields"][0]["field"] == "monitor_instance_active"
    assert "ops-gauge-cpu" not in by_id
    assert "ops-gauge-memory" not in by_id
    assert "ops-gauge-disk" not in by_id
    host_metrics = by_id["ops-host-key-metrics"]
    assert host_metrics["name"] == "主机关键指标"
    assert (host_metrics["x"], host_metrics["y"], host_metrics["w"], host_metrics["h"]) == (10, 0, 8, 8)
    assert host_metrics["valueConfig"]["chartType"] == "topN"
    assert host_metrics["valueConfig"]["barMode"] == "absolute"
    assert host_metrics["valueConfig"]["barMax"] == 100
    assert host_metrics["valueConfig"]["unitId"] == "percent"
    assert host_metrics["valueConfig"]["topNScalarFields"] == [
        {"field": "avg_cpu", "label": "CPU 使用率"},
        {"field": "avg_memory", "label": "内存使用率"},
        {"field": "avg_disk", "label": "磁盘使用率"},
    ]
    assert "topNLabelField" not in host_metrics["valueConfig"]
    assert host_metrics["valueConfig"].get("compare") is not True
    assert host_metrics["valueConfig"]["interaction"]["url"] == "/monitor/view/dashboard/host"
    scope = next(param for param in host_metrics["valueConfig"]["dataSourceParams"] if param["name"] == "scope")
    assert scope["value"] == "all_authorized"
    assert scope["alias_name"] == "主机范围"
    assert [param["type"] for param in host_metrics["valueConfig"]["dataSourceParams"] if param["type"] in {"timeRange", "dateRange"}] == [
        "timeRange"
    ]
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
    monitor_columns = by_id["ops-monitor-alerts"]["valueConfig"]["tableConfig"]["columns"]
    assert [column["key"] for column in monitor_columns] == [
        "monitor_instance_name",
        "metric_name",
        "value",
        "level",
    ]
    assert monitor_columns[3]["title"] == "状态"
    assert monitor_columns[3]["cellType"] == "colorBackground"
    assert any(item["value"] == "critical" and item["result"]["text"] == "严重" for item in monitor_columns[3]["valueMappings"])
    alert_columns = by_id["ops-alert-top"]["valueConfig"]["tableConfig"]["columns"]
    assert [column["key"] for column in alert_columns] == [
        "resource_name",
        "title",
        "level",
        "created_at",
    ]
    assert alert_columns[2]["cellType"] == "colorBackground"
    assert any(item["value"] == "严重" and item["result"]["color"] == "#F43B2C" for item in alert_columns[2]["valueMappings"])
    assert by_id["ops-kpi-resources"]["valueConfig"]["interaction"]["url"] == "/cmdb/assetOverview"
    assert by_id["ops-app-top"]["valueConfig"]["interaction"]["name"] == "查看全部"
    assert "节点用法总览::node/get_node_usage_statistics" in dashboard.refs.datasource_keys
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

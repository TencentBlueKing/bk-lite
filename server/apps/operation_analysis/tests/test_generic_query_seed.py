"""内置通用查询种子：分析方式、枚举和分页默认值。"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.alerts.constants.constants import AlertStatus, EventLevel, EventStatus
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorEvent

SEED = Path(__file__).resolve().parents[1] / "support-files" / "source_api.json"


def _sources():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return {
        item["rest_api"]: item
        for item in data
        if item.get("key", "").endswith(f"::{item.get('rest_api')}")
        and item["rest_api"]
        in {
            "cmdb/query_cmdb_models",
            "cmdb/query_cmdb_instances",
            "cmdb/query_cmdb_one_hop",
            "monitor/query_monitor_instances",
            "monitor/query_monitor_metric",
            "monitor/query_monitor_alerts",
            "alert/query_alert_center",
        }
    }


def _param(source, name):
    return next(item for item in source["params"] if item["name"] == name)


def _option_values(param):
    return {item["value"] for item in param["inputConfig"]["optionsSource"]["staticItems"]}


def test_generic_query_seed_declares_analysis_modes_and_paging_defaults():
    sources = _sources()
    assert set(sources) == {
        "cmdb/query_cmdb_models",
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_one_hop",
        "monitor/query_monitor_instances",
        "monitor/query_monitor_metric",
        "monitor/query_monitor_alerts",
        "alert/query_alert_center",
    }
    for source in sources.values():
        visible = [param["name"] for param in source["params"] if not param.get("hidden") and param.get("filterType") != "filter"]
        assert visible[0] == "analysis_mode"
        mode = _param(source, "analysis_mode")
        assert "componentSwitch" not in mode.get("inputConfig", {})
        options = mode["inputConfig"]["optionsSource"]["staticItems"]
        assert options
        for option in options:
            assert option["charts"]
            assert option["result"]["structure"] in {"table", "value", "category", "series"}
            assert set(option["charts"]) <= set(source["chart_type"])
        has_page = any(param["name"] == "page" for param in source["params"])
        if source["rest_api"] == "monitor/query_monitor_metric":
            assert has_page is False
        else:
            assert has_page is True
            assert _param(source, "page")["value"] is None
            assert _param(source, "page_size")["value"] is None
            assert "visible_modes" not in _param(source, "page")
            assert "visible_charts" not in _param(source, "page_size")


def test_generic_query_seed_enums_match_module_constants():
    sources = _sources()
    levels = _option_values(_param(sources["monitor/query_monitor_alerts"], "level"))
    assert levels == {"warning", "error", "critical", "no_data"}
    assert "info" not in levels
    assert levels <= {value for value, _label in MonitorEvent.LEVEL_CHOICES}
    statuses = _option_values(_param(sources["monitor/query_monitor_alerts"], "status"))
    assert statuses <= {value for value, _label in MonitorAlert.STATUS_CHOICES}
    alert_levels = _option_values(_param(sources["alert/query_alert_center"], "level"))
    assert alert_levels <= {value for value, _label in EventLevel.CHOICES}
    alert_statuses = _option_values(_param(sources["alert/query_alert_center"], "status"))
    allowed_status = {value for value, _label in EventStatus.CHOICES + AlertStatus.CHOICES}
    assert alert_statuses <= allowed_status

    center = sources["alert/query_alert_center"]

    def objects_for(param_name, value):
        item = next(option for option in _param(center, param_name)["inputConfig"]["optionsSource"]["staticItems"] if option["value"] == value)
        return set(item.get("query_objects") or ["alert", "event"])

    assert objects_for("status", "received") == {"event"}
    assert objects_for("status", "unassigned") == {"alert"}
    assert objects_for("status", "pending") == {"alert", "event"}
    assert objects_for("time_field", "created_at") == {"alert"}
    assert objects_for("time_field", "received_at") == {"event"}
    assert objects_for("group_by", "source_name") == {"alert", "event"}
    assert objects_for("group_by", "level") == {"alert", "event"}


def test_generic_query_seed_uses_chart_driven_filters_and_order():
    sources = _sources()
    models = sources["cmdb/query_cmdb_models"]
    model = _param(models, "model_id")
    assert model["inputConfig"]["optionsSource"]["queryParams"]["classification_id"] == {"ref": "classification_id"}
    assert model["inputConfig"]["optionsSource"]["emptyUpstreamHintKey"] == "dashboard.selectClassificationFirst"
    for rest_api in (
        "cmdb/query_cmdb_models",
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_one_hop",
        "monitor/query_monitor_instances",
        "monitor/query_monitor_alerts",
        "alert/query_alert_center",
    ):
        source = sources[rest_api]
        modes = {item["value"]: item["charts"] for item in _param(source, "analysis_mode")["inputConfig"]["optionsSource"]["staticItems"]}
        if rest_api == "monitor/query_monitor_instances":
            assert list(modes) == ["detail"]
            assert modes["detail"] == ["table"]
            assert source["chart_type"] == ["table"]
            names = {param["name"] for param in source["params"]}
            assert "group_by" not in names
            assert "filters" not in names
            continue
        assert "topN" not in modes["detail"]
        assert "topN" in modes["distribution"]
        names = [param["name"] for param in source["params"]]
        if rest_api in {"cmdb/query_cmdb_models", "cmdb/query_cmdb_one_hop"}:
            assert "order" not in names
        else:
            assert _param(source, "order")["inputConfig"]["control"] == "order"
    model_names = [param["name"] for param in models["params"]]
    assert "result_filter" not in model_names
    assert "result_op" not in model_names
    assert "count_metric" not in model_names
    assert "top_n" not in model_names
    group_by = _param(sources["cmdb/query_cmdb_instances"], "group_by")
    assert group_by["alias_name"] == "分布属性"
    for rest_api in (
        "monitor/query_monitor_alerts",
        "alert/query_alert_center",
    ):
        assert _param(sources[rest_api], "group_by")["value"] == ""
    assert "每种取值" in group_by["desc"]
    instance_fields = _param(sources["cmdb/query_cmdb_instances"], "filters")["inputConfig"]["fields"]
    assert instance_fields["kind"] == "dynamic"
    assert instance_fields["sourceRef"]["value"] == "cmdb/list_cmdb_attr_options"
    assert instance_fields["valueField"] == "attr_id"
    assert instance_fields["labelField"] == "attr_name"
    assert instance_fields["queryParams"]["model_id"] == {"ref": "model_id"}
    end_fields = _param(sources["cmdb/query_cmdb_one_hop"], "end_filters")["inputConfig"]["fields"]
    assert end_fields["kind"] == "dynamic"
    assert end_fields["queryParams"]["start_model_id"] == {"ref": "start_model_id"}
    assert end_fields["queryParams"]["model_asst_id"] == {"ref": "model_asst_id"}
    center = sources["alert/query_alert_center"]
    assert "filters" not in {param["name"] for param in center["params"]}
    for name in ("source", "level", "status"):
        assert _param(center, name).get("hidden") is not True
    assert _param(center, "source")["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "alert/list_alert_source_options"
    metric = sources["monitor/query_monitor_metric"]
    metric_filters = _param(metric, "filters")
    assert metric_filters["type"] == "conditionFilter"
    assert metric_filters["inputConfig"]["fields"]["queryParams"]["metric_id"] == {"ref": "metric_id"}
    assert metric_filters["inputConfig"]["fields"]["sourceRef"]["value"] == "monitor/list_metric_dimensions"
    assert "dimension_label" not in {param["name"] for param in metric["params"]}
    assert metric["chart_type"] == ["line", "table"]
    series_mode = next(item for item in _param(metric, "analysis_mode")["inputConfig"]["optionsSource"]["staticItems"] if item["value"] == "series")
    assert series_mode["charts"] == ["line"]
    aggregation = _param(metric, "aggregation")
    assert aggregation["required"] is False
    assert aggregation["value"] == "avg"
    assert _param(metric, "metric_id")["inputConfig"]["optionsSource"]["labelField"] == "option_label"
    assert _param(metric, "metric_id")["inputConfig"]["optionsSource"]["queryParams"] == {"monitor_obj_id": {"ref": "monitor_object_id"}}
    visible = [item["name"] for item in metric["params"] if not item.get("hidden")]
    assert visible.index("monitor_object_id") < visible.index("instance_ids") < visible.index("metric_id")
    metric_fields = {field["key"]: field for field in metric["field_schema"]}
    assert "status" not in metric_fields
    assert "dimension" not in metric_fields
    assert metric_fields["time"]["modes"] == ["series", "latest"]
    assert metric_fields["instance_id"]["modes"] == ["latest", "value"]


def test_instance_and_one_hop_classification_is_single_select_and_declared():
    from apps.operation_analysis.views.datasource_view import _resolve_request_params

    sources = _sources()
    specs = (
        ("cmdb/query_cmdb_instances", "model_id"),
        ("cmdb/query_cmdb_one_hop", "start_model_id"),
    )
    for rest_api, model_name in specs:
        source = sources[rest_api]
        classification = _param(source, "classification_id")
        options = classification["inputConfig"]["optionsSource"]
        assert classification["inputConfig"]["control"] == "select"
        assert classification["inputConfig"].get("multiple") is not True
        assert options["valueField"] == "classification_id"
        assert options["sourceRef"]["value"] == "cmdb/get_model_classification_options"
        model = _param(source, model_name)
        model_options = model["inputConfig"]["optionsSource"]
        assert model["inputConfig"].get("multiple") is not True
        assert model_options["queryParams"]["classification_id"] == {"ref": "classification_id"}
        assert model_options["emptyUpstreamHintKey"] == "dashboard.selectClassificationFirst"
        visible = [item["name"] for item in source["params"] if not item.get("hidden")]
        assert visible.index("classification_id") < visible.index(model_name)
        instance = SimpleNamespace(rest_api=rest_api, params=source["params"])
        resolved = _resolve_request_params(
            instance,
            {"classification_id": "compute", model_name: "host", "analysis_mode": "detail"},
        )
        assert resolved["classification_id"] == "compute"
        assert resolved[model_name] == "host"
        with pytest.raises(ValueError, match="未声明参数"):
            _resolve_request_params(instance, {"classification_id": "compute", "not_declared": "x"})

    one_hop = sources["cmdb/query_cmdb_one_hop"]
    visible = [item["name"] for item in one_hop["params"] if not item.get("hidden")]
    assert visible.index("classification_id") < visible.index("start_model_id") < visible.index("model_asst_id")
    assert "end_filter_field" not in visible
    assert "filter_field" not in visible
    association = _param(one_hop, "model_asst_id")["inputConfig"]["optionsSource"]
    assert association["queryParams"]["model_id"] == {"ref": "start_model_id"}
    start_fields = _param(one_hop, "filters")["inputConfig"]["fields"]
    assert start_fields["kind"] == "dynamic"
    assert start_fields["queryParams"]["model_id"] == {"ref": "start_model_id"}
    assert _param(one_hop, "end_filters")["inputConfig"]["fields"]["kind"] == "dynamic"
    kept = _resolve_request_params(
        SimpleNamespace(rest_api="cmdb/query_cmdb_one_hop", params=one_hop["params"]),
        {"start_model_id": "host", "order": "start_name", "direction": "out"},
    )
    assert kept["start_model_id"] == "host"
    assert "order" not in kept
    assert "direction" not in kept


def test_model_query_schema_matches_detail_rows_without_touching_other_status():
    sources = _sources()
    models = sources["cmdb/query_cmdb_models"]
    assert [field["key"] for field in models["field_schema"]] == [
        "classification_name",
        "model_name",
        "model_id",
        "instance_count",
        "model_count",
    ]
    assert models["field_schema"][1]["role"] == "dimension"
    assert models["field_schema"][2]["role"] == "identity"
    assert models["field_schema"][4]["modes"] == ["count"]
    assert models["field_schema"][4]["table"] is False
    assert "各模型权限内实例数" in models["desc"]
    assert "页码不参与" in models["desc"]
    assert "每页 10" not in models["desc"]
    assert _param(models, "page_size")["alias_name"] == "每页条数/返回条数"
    for rest_api in (
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_one_hop",
        "monitor/query_monitor_instances",
        "monitor/query_monitor_alerts",
        "alert/query_alert_center",
    ):
        assert _param(sources[rest_api], "page_size")["alias_name"] == "每页条数/返回条数"
    assert "分类汇总" not in models["desc"]
    assert "模型数量" in models["desc"]
    assert "实例总数" not in models["desc"]
    assert "空模型" not in models["desc"]
    assert "非空" not in models["desc"]
    assert "TOP5" not in models["desc"]
    assert _param(models, "analysis_mode")["value"] == "detail"
    assert _param(models, "page")["value"] is None
    assert _param(models, "page_size")["value"] is None
    assert models["chart_type"] == ["table", "topN", "single", "bar", "pie"]
    assert models["rest_api"] == "cmdb/query_cmdb_models"
    for rest_api, source in sources.items():
        names = [param["name"] for param in source["params"]]
        assert "top_n" not in names
        assert "count_metric" not in names
        if rest_api != "cmdb/query_cmdb_models":
            assert "result_filter" not in names
    alerts = sources["monitor/query_monitor_alerts"]
    assert "页码" in alerts["desc"]
    assert any(item["name"] == "page" for item in alerts["params"])
    assert any(item["name"] == "page_size" for item in alerts["params"])
    options = next(
        item
        for item in json.loads(SEED.read_text(encoding="utf-8"))
        if isinstance(item, dict) and item.get("key") == "监控对象列表::monitor/monitor_objects"
    )
    assert options["rest_api"] == "monitor/list_monitor_object_options"
    assert any(field["key"] == "display_name" for field in options["field_schema"])
    center = sources["alert/query_alert_center"]
    assert "status" in {field["key"] for field in alerts["field_schema"]}
    alert_names = {param["name"] for param in alerts["params"]}
    assert "filters" not in alert_names
    assert "instance_id" not in alert_names
    assert "instance_ids" in alert_names
    assert _param(alerts, "monitor_object_id").get("required") is not True
    assert _param(alerts, "instance_ids")["inputConfig"]["multiple"] is True
    assert _param(alerts, "level")["inputConfig"]["multiple"] is True
    assert _param(alerts, "instance_ids")["inputConfig"]["optionsSource"]["queryParams"]["monitor_object_id"] == {"ref": "monitor_object_id"}
    assert "updated_at" not in _option_values(_param(alerts, "time_field"))
    assert "monitor_object_id" in _option_values(_param(alerts, "group_by"))
    assert "不选分组会失败" in _param(alerts, "group_by")["desc"]
    value_field = next(field for field in alerts["field_schema"] if field["key"] == "value")
    assert value_field["title"] == "告警值"
    content = next(field for field in alerts["field_schema"] if field["key"] == "content")
    assert content["title"] == "告警名称"
    object_name = next(field for field in alerts["field_schema"] if field["key"] == "monitor_object_name")
    assert "展示名" in object_name["description"]
    assert next(field for field in alerts["field_schema"] if field["key"] == "id")["table"] is False
    assert next(field for field in alerts["field_schema"] if field["key"] == "monitor_object_id")["table"] is False
    assert "updated_at" not in {field["key"] for field in alerts["field_schema"]}
    assert "status" in {field["key"] for field in center["field_schema"]}

    def query_objects_for(key):
        field = next(item for item in center["field_schema"] if item["key"] == key)
        return set(field.get("query_objects") or ["alert", "event"])

    assert query_objects_for("alert_id") == {"alert"}
    assert query_objects_for("event_id") == {"event"}
    assert query_objects_for("source_name") == {"alert", "event"}
    source_id = next(item for item in center["field_schema"] if item["key"] == "source_id")
    assert source_id["modes"] == ["detail"]
    assert query_objects_for("source_id") == {"event"}
    instances = sources["monitor/query_monitor_instances"]
    assert "status" in {field["key"] for field in instances["field_schema"]}
    assert "instance_count" not in {field["key"] for field in instances["field_schema"]}
    assert "cmdb_bind_status" not in {field["key"] for field in instances["field_schema"]}
    assert "unit" not in {field["key"] for field in instances["field_schema"]}
    instance_query = sources["cmdb/query_cmdb_instances"]
    one_hop = sources["cmdb/query_cmdb_one_hop"]
    metric = sources["monitor/query_monitor_metric"]
    models = sources["cmdb/query_cmdb_models"]

    def table_keys(source):
        return [field["key"] for field in source["field_schema"] if field.get("table") is not False]

    assert table_keys(instance_query) == ["inst_name"]
    assert table_keys(one_hop) == ["start_name", "end_name"]
    assert one_hop["chart_type"] == ["table", "single", "topN"]
    distribution = next(
        item for item in _param(one_hop, "analysis_mode")["inputConfig"]["optionsSource"]["staticItems"] if item["value"] == "distribution"
    )
    assert distribution["charts"] == ["topN"]
    assert "order" not in {param["name"] for param in one_hop["params"]}
    assert "direction" not in {param["name"] for param in one_hop["params"]}
    relation = next(field for field in one_hop["field_schema"] if field["key"] == "relation_count")
    assert relation["modes"] == ["count", "distribution"]
    assert "start_count" not in {field["key"] for field in one_hop["field_schema"]}
    assert "status" not in table_keys(instance_query)
    assert table_keys(instances) == [
        "instance_id",
        "name",
        "ip",
        "cloud_region",
        "cmdb_id",
        "monitor_object_id",
        "status",
    ]
    object_field = next(field for field in instances["field_schema"] if field["key"] == "monitor_object_id")
    assert object_field["title"] == "监控对象"
    assert "展示名" in object_field["description"]
    assert [field["value"] for field in _param(instances, "order")["inputConfig"]["fields"]] == ["name", "ip"]
    for rest_api in (
        "monitor/query_monitor_instances",
        "monitor/query_monitor_metric",
        "monitor/query_monitor_alerts",
    ):
        options = _param(sources[rest_api], "monitor_object_id")["inputConfig"]["optionsSource"]
        assert options["valueField"] == "id"
        assert options["labelField"] == "display_name"
    assert "value" in table_keys(alerts)
    assert "name" not in table_keys(alerts)
    assert "status" in table_keys(center)
    assert "unit" not in table_keys(center)
    assert all(field.get("table") is not False for field in metric["field_schema"])
    assert [field["key"] for field in models["field_schema"]] == [
        "classification_name",
        "model_name",
        "model_id",
        "instance_count",
        "model_count",
    ]
    assert models["field_schema"][1]["role"] == "dimension"
    assert models["field_schema"][2]["role"] == "identity"
    assert models["field_schema"][4]["modes"] == ["count"]
    assert models["field_schema"][4]["table"] is False


def test_model_query_resolver_keeps_explicit_values_and_skips_hidden_defaults():
    from apps.operation_analysis.views.datasource_view import _resolve_request_params

    models = _sources()["cmdb/query_cmdb_models"]
    instance = SimpleNamespace(rest_api="cmdb/query_cmdb_models", params=models["params"])
    distribution = _resolve_request_params(
        instance,
        {"analysis_mode": "distribution", "classification_id": "compute"},
    )
    explicit = _resolve_request_params(
        instance,
        {"analysis_mode": "distribution", "page": 2, "page_size": 20},
    )
    cleared = _resolve_request_params(
        instance,
        {"analysis_mode": "count", "page": None, "page_size": ""},
    )
    refilled = SimpleNamespace(
        rest_api="cmdb/query_cmdb_models",
        params=[
            {"name": "analysis_mode", "type": "string", "value": "count", "filterType": "params"},
            {"name": "page", "type": "number", "value": 1, "filterType": "params"},
            {"name": "page_size", "type": "number", "value": 10, "filterType": "params"},
        ],
    )
    omitted = _resolve_request_params(refilled, {"analysis_mode": "count", "page": None, "page_size": ""})
    detail = _resolve_request_params(instance, {"analysis_mode": "detail"})
    legacy = SimpleNamespace(
        rest_api="legacy/query",
        params=[
            {"name": "page", "type": "number", "value": 2, "filterType": "params"},
            {"name": "page_size", "type": "number", "value": 15, "filterType": "params"},
        ],
    )
    kept = _resolve_request_params(legacy, {})

    assert "page" not in distribution
    assert "page_size" not in distribution
    assert explicit["page"] == 2
    assert explicit["page_size"] == 20
    assert "page" not in cleared
    assert "page_size" not in cleared
    assert omitted == {"analysis_mode": "count"}
    assert "page" not in detail
    assert "page_size" not in detail
    assert kept == {"page": 2, "page_size": 15}
    passed = _resolve_request_params(legacy, {"page": None, "page_size": ""})
    assert passed["page"] is None
    assert passed["page_size"] == ""
    legacy_time = SimpleNamespace(
        rest_api="legacy/query",
        params=[
            {"name": "time", "type": "timeRange", "value": 10080, "filterType": "params"},
            {"name": "page", "type": "number", "value": 2, "filterType": "params"},
        ],
    )
    cleared_time = _resolve_request_params(legacy_time, {"time": "", "page": None})
    assert "time" not in cleared_time
    assert cleared_time["page"] is None

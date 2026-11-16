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
            "cmdb/query_cmdb_model_counts",
            "cmdb/query_cmdb_instances",
            "cmdb/query_cmdb_instance_value",
            "cmdb/query_cmdb_instance_distribution",
            "cmdb/query_cmdb_one_hop",
            "cmdb/query_cmdb_one_hop_counts",
            "cmdb/query_cmdb_one_hop_distribution",
            "monitor/query_monitor_instances",
            "monitor/query_monitor_metric",
            "monitor/query_monitor_alerts",
            "monitor/query_monitor_alert_counts",
            "monitor/query_monitor_alert_distribution",
            "alert/query_alert_center",
            "alert/query_alert_center_counts",
            "alert/query_alert_center_distribution",
        }
    }


def _param(source, name):
    return next(item for item in source["params"] if item["name"] == name)


def _option_values(param):
    return {item["value"] for item in param["inputConfig"]["optionsSource"]["staticItems"]}


def test_monitor_instance_count_source_is_one_object_and_one_number():
    data = json.loads(SEED.read_text(encoding="utf-8"))
    matches = [item for item in data if item.get("rest_api") == "monitor/query_monitor_instance_counts"]
    assert len(matches) == 1
    source = matches[0]
    assert source["key"] == "监控实例数量统计::monitor/query_monitor_instance_counts"
    assert source["name"] == "监控实例数量统计"
    assert source["chart_type"] == ["single", "gauge"]
    names = [param["name"] for param in source["params"]]
    assert names == ["monitor_object_id", "status", "organization"]
    monitor_object = _param(source, "monitor_object_id")
    assert monitor_object["required"] is True
    assert monitor_object["inputConfig"].get("multiple") is not True
    assert monitor_object["inputConfig"]["optionsSource"]["valueField"] == "id"
    assert monitor_object["inputConfig"]["optionsSource"]["labelField"] == "display_name"
    assert _param(source, "status")["value"] == "all"
    assert [field["key"] for field in source["field_schema"]] == ["instance_count"]
    for dropped in ("page", "page_size", "order_by", "order_dir", "instance_ids", "analysis_mode"):
        assert dropped not in names


def test_generic_query_seed_declares_analysis_modes_and_paging_defaults():
    sources = _sources()
    assert set(sources) == {
        "cmdb/query_cmdb_models",
        "cmdb/query_cmdb_model_counts",
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_instance_value",
        "cmdb/query_cmdb_instance_distribution",
        "cmdb/query_cmdb_one_hop",
        "cmdb/query_cmdb_one_hop_counts",
        "cmdb/query_cmdb_one_hop_distribution",
        "monitor/query_monitor_instances",
        "monitor/query_monitor_metric",
        "monitor/query_monitor_alerts",
        "monitor/query_monitor_alert_counts",
        "monitor/query_monitor_alert_distribution",
        "alert/query_alert_center",
        "alert/query_alert_center_counts",
        "alert/query_alert_center_distribution",
    }
    no_page = {
        "monitor/query_monitor_metric",
        "monitor/query_monitor_alert_counts",
        "monitor/query_monitor_alert_distribution",
        "cmdb/query_cmdb_model_counts",
        "cmdb/query_cmdb_instance_value",
        "cmdb/query_cmdb_one_hop_counts",
        "alert/query_alert_center_counts",
    }
    limit_only = {
        "cmdb/query_cmdb_instance_distribution",
        "cmdb/query_cmdb_one_hop_distribution",
        "alert/query_alert_center_distribution",
    }
    for source in sources.values():
        names = [param["name"] for param in source["params"]]
        assert "analysis_mode" not in names
        if source["rest_api"] in no_page:
            assert "page" not in names
            assert "page_size" not in names
        elif source["rest_api"] in limit_only:
            assert "page" not in names
            assert _param(source, "page_size")["value"] is None
            assert _param(source, "page_size")["alias_name"] == "返回条数"
            assert "超过 500" in source["desc"]
            assert "填写后只返回排序后的前 N 条" in source["desc"]
            assert "填写后只返回排序后的前 N 条" in _param(source, "page_size")["desc"]
        else:
            assert _param(source, "page")["value"] is None
            assert _param(source, "page_size")["value"] is None
            assert "visible_modes" not in _param(source, "page")
            assert "visible_charts" not in _param(source, "page_size")
        for field in source.get("field_schema") or []:
            assert "table" not in field
            assert "query_objects" not in field
        for param in source["params"]:
            assert "visible_modes" not in param
            items = ((param.get("inputConfig") or {}).get("optionsSource") or {}).get("staticItems") or []
            for item in items:
                assert "query_objects" not in item
                assert "charts" not in item
                assert "result" not in item


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
    for rest_api in (
        "alert/query_alert_center",
        "alert/query_alert_center_counts",
        "alert/query_alert_center_distribution",
    ):
        shared = sources[rest_api]
        assert "received" in _option_values(_param(shared, "status"))
        assert "unassigned" in _option_values(_param(shared, "status"))
        assert "pending" in _option_values(_param(shared, "status"))
        assert "created_at" in _option_values(_param(shared, "time_field"))
        assert "received_at" in _option_values(_param(shared, "time_field"))
    distribution = sources["alert/query_alert_center_distribution"]
    assert "source_name" in _option_values(_param(distribution, "group_by"))
    assert "level" in _option_values(_param(distribution, "group_by"))
    assert "group_by" not in {param["name"] for param in center["params"]}


def test_generic_query_seed_uses_chart_driven_filters_and_order():
    sources = _sources()
    models = sources["cmdb/query_cmdb_models"]
    model = _param(models, "model_id")
    assert model["inputConfig"]["optionsSource"]["queryParams"]["classification_id"] == {"ref": "classification_id"}
    assert model["inputConfig"]["optionsSource"]["emptyUpstreamHintKey"] == "dashboard.selectClassificationFirst"
    instances = sources["monitor/query_monitor_instances"]
    instance_names = {param["name"] for param in instances["params"]}
    assert "analysis_mode" not in instance_names
    assert instances["chart_type"] == ["table"]
    assert "group_by" not in instance_names
    assert "filters" not in instance_names
    assert "order" not in instance_names
    assert "order_by" not in instance_names
    assert "order_dir" not in instance_names
    for rest_api in (
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_instance_distribution",
        "cmdb/query_cmdb_one_hop",
        "alert/query_alert_center",
        "alert/query_alert_center_distribution",
    ):
        source = sources[rest_api]
        names = [param["name"] for param in source["params"]]
        assert "analysis_mode" not in names
        assert "group_by" not in names or rest_api.endswith("distribution")
        if rest_api == "cmdb/query_cmdb_one_hop":
            assert "order" not in names
            assert "order_by" not in names
        else:
            assert "order" not in names
            assert _param(source, "order_by")["type"] == "string"
            assert _param(source, "order_by")["value"] == ""
            assert _param(source, "order_dir")["type"] == "string"
            assert _param(source, "order_dir")["value"] == ""
            assert _param(source, "order_by").get("required") is not True
            assert _param(source, "order_dir").get("required") is not True
    model_names = [param["name"] for param in models["params"]]
    assert "analysis_mode" not in model_names
    assert "result_filter" not in model_names
    assert "result_op" not in model_names
    assert "count_metric" not in model_names
    assert "top_n" not in model_names
    group_by = _param(sources["cmdb/query_cmdb_instance_distribution"], "group_by")
    assert group_by["alias_name"] == "分布属性"
    assert group_by["required"] is True
    assert _param(sources["alert/query_alert_center_distribution"], "group_by")["value"] == ""
    assert _param(sources["alert/query_alert_center_distribution"], "group_by")["required"] is True
    assert "group_by" not in {param["name"] for param in sources["cmdb/query_cmdb_instances"]["params"]}
    alerts = sources["monitor/query_monitor_alerts"]
    counts = sources["monitor/query_monitor_alert_counts"]
    for source in (alerts, counts):
        names = {param["name"] for param in source["params"]}
        assert "analysis_mode" not in names
        assert "group_by" not in names
    assert _param(alerts, "time_range")["filterType"] == "params"
    assert _param(counts, "time_range")["filterType"] == "params"
    assert _param(alerts, "time_field")["filterType"] == "params"
    assert _param(alerts, "order_by")["type"] == "string"
    assert _param(alerts, "order_by")["value"] == ""
    assert _param(alerts, "order_dir")["value"] == ""
    count_names = {param["name"] for param in counts["params"]}
    assert "order_by" not in count_names
    assert "page" not in count_names
    assert "每种取值" in group_by["desc"]
    instance_fields = _param(sources["cmdb/query_cmdb_instances"], "filters")["inputConfig"]["fields"]
    assert instance_fields["kind"] == "dynamic"
    assert instance_fields["sourceRef"]["value"] == "cmdb/list_cmdb_attr_options"
    assert instance_fields["valueField"] == "attr_id"
    assert instance_fields["labelField"] == "attr_name"
    assert instance_fields["queryParams"]["model_id"] == {"ref": "model_id"}
    order_by = _param(sources["cmdb/query_cmdb_instances"], "order_by")
    assert order_by["inputConfig"]["control"] == "select"
    assert order_by["inputConfig"]["optionsSource"] == group_by["inputConfig"]["optionsSource"]
    for rest_api in (
        "cmdb/query_cmdb_one_hop",
        "cmdb/query_cmdb_one_hop_counts",
        "cmdb/query_cmdb_one_hop_distribution",
    ):
        names = {param["name"] for param in sources[rest_api]["params"]}
        assert "filters" not in names
        assert "end_filters" not in names
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
    assert "analysis_mode" not in {param["name"] for param in metric["params"]}
    assert metric["chart_type"] == ["line", "bar", "table"]
    aggregation = _param(metric, "aggregation")
    assert aggregation["alias_name"] == "实例合并"
    assert aggregation["required"] is False
    assert aggregation["value"] == ""
    assert _option_values(aggregation) == {"avg", "sum", "max", "min"}
    step = _param(metric, "step")
    assert step["required"] is False
    assert step["value"] == ""
    instance_picker = _param(metric, "instance_ids")["inputConfig"]["optionsSource"]["queryParams"]
    assert "analysis_mode" not in instance_picker
    assert _param(metric, "metric_id")["inputConfig"]["optionsSource"]["labelField"] == "option_label"
    assert _param(metric, "metric_id")["inputConfig"]["optionsSource"]["queryParams"] == {"monitor_obj_id": {"ref": "monitor_object_id"}}
    visible = [item["name"] for item in metric["params"] if not item.get("hidden")]
    assert visible.index("monitor_object_id") < visible.index("instance_ids") < visible.index("metric_id")
    metric_fields = {field["key"]: field for field in metric["field_schema"]}
    assert "status" not in metric_fields
    assert "dimension" not in metric_fields
    assert "aggregation" not in metric_fields
    assert metric_fields["time"]["value_type"] == "datetime"
    assert metric_fields["value"]["value_type"] == "number"
    assert "chart_role" not in metric_fields["time"]
    assert "chart_role" not in metric_fields["value"]
    assert "chart_role" not in metric_fields["series"]
    assert [field["key"] for field in metric["field_schema"]] == [
        "series",
        "instance_id",
        "instance_name",
        "time",
        "value",
        "unit",
    ]


def test_instance_and_one_hop_classification_is_single_select_and_declared():
    from apps.operation_analysis.views.datasource_view import _resolve_request_params

    sources = _sources()
    specs = (
        ("cmdb/query_cmdb_instances", "model_id"),
        ("cmdb/query_cmdb_instance_value", "model_id"),
        ("cmdb/query_cmdb_instance_distribution", "model_id"),
        ("cmdb/query_cmdb_one_hop", "start_model_id"),
        ("cmdb/query_cmdb_one_hop_counts", "start_model_id"),
        ("cmdb/query_cmdb_one_hop_distribution", "start_model_id"),
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
            {"classification_id": "compute", model_name: "host"},
        )
        assert resolved["classification_id"] == "compute"
        assert resolved[model_name] == "host"
        with pytest.raises(ValueError, match="未声明参数"):
            _resolve_request_params(instance, {"classification_id": "compute", "not_declared": "x"})

    one_hop = sources["cmdb/query_cmdb_one_hop"]
    visible = [item["name"] for item in one_hop["params"] if not item.get("hidden")]
    assert visible.index("classification_id") < visible.index("start_model_id") < visible.index("model_asst_id")
    declared = [item["name"] for item in one_hop["params"]]
    assert "end_filter_field" not in declared
    assert "filter_field" not in declared
    instance_names = [item["name"] for item in sources["cmdb/query_cmdb_instances"]["params"]]
    assert "filter_field" not in instance_names
    assert "filter_op" not in instance_names
    assert "filter_value" not in instance_names
    association = _param(one_hop, "model_asst_id")
    assert association["inputConfig"]["multiple"] is True
    assert association["value"] == []
    assert association["inputConfig"]["optionsSource"]["queryParams"]["model_id"] == {"ref": "start_model_id"}
    for rest_api in (
        "cmdb/query_cmdb_one_hop_counts",
        "cmdb/query_cmdb_one_hop_distribution",
    ):
        relation = _param(sources[rest_api], "model_asst_id")
        assert relation["inputConfig"]["multiple"] is True
        assert relation["value"] == []
    kept = _resolve_request_params(
        SimpleNamespace(rest_api="cmdb/query_cmdb_one_hop", params=one_hop["params"]),
        {"start_model_id": "host"},
    )
    assert kept["start_model_id"] == "host"
    with pytest.raises(ValueError, match="未声明参数"):
        _resolve_request_params(
            SimpleNamespace(rest_api="cmdb/query_cmdb_one_hop", params=one_hop["params"]),
            {"start_model_id": "host", "order": "start_name", "direction": "out"},
        )
    for rest_api in (
        "cmdb/query_cmdb_one_hop",
        "cmdb/query_cmdb_one_hop_counts",
        "cmdb/query_cmdb_one_hop_distribution",
    ):
        source = sources[rest_api]
        dropped = _resolve_request_params(
            SimpleNamespace(rest_api=rest_api, params=source["params"]),
            {
                "start_model_id": "host",
                "filters": {"logic": "AND", "items": [{"field": "cpu", "op": "gt", "value": 1}]},
                "end_filters": {"logic": "AND", "items": [{"field": "port", "op": "eq", "value": "80"}]},
            },
        )
        assert dropped["start_model_id"] == "host"
        assert "filters" not in dropped
        assert "end_filters" not in dropped


def test_model_query_schema_matches_detail_rows_without_touching_other_status():
    sources = _sources()
    models = sources["cmdb/query_cmdb_models"]
    assert [field["key"] for field in models["field_schema"]] == [
        "classification_name",
        "model_name",
        "model_id",
        "instance_count",
    ]
    assert "chart_role" not in models["field_schema"][1]
    assert "chart_role" not in models["field_schema"][3]
    assert "chart_role" not in sources["cmdb/query_cmdb_model_counts"]["field_schema"][0]
    assert "不填页码" in models["desc"]
    assert "零实例" in models["desc"]
    assert "每页 10" not in models["desc"]
    assert _param(models, "page_size")["alias_name"] == "每页条数"
    for rest_api in (
        "cmdb/query_cmdb_instances",
        "cmdb/query_cmdb_one_hop",
        "alert/query_alert_center",
    ):
        assert _param(sources[rest_api], "page_size")["alias_name"] == "每页条数"
        assert _param(sources[rest_api], "page").get("required") is not True
        assert _param(sources[rest_api], "page_size").get("required") is not True
        assert "不填页码" in sources[rest_api]["desc"]
    assert "500" in sources["cmdb/query_cmdb_instances"]["desc"]
    assert "1000" in sources["cmdb/query_cmdb_one_hop"]["desc"]
    assert "500" in sources["alert/query_alert_center"]["desc"]
    assert _param(sources["monitor/query_monitor_alerts"], "page_size")["alias_name"] == "每页条数"
    assert _param(sources["monitor/query_monitor_instances"], "page_size")["alias_name"] == "每页条数"
    assert "不填页码" in sources["monitor/query_monitor_instances"]["desc"]
    assert "分类汇总" not in models["desc"]
    assert "实例总数" not in models["desc"]
    assert "空模型" not in models["desc"]
    assert "非空" not in models["desc"]
    assert "TOP5" not in models["desc"]
    assert _param(models, "page")["value"] is None
    assert _param(models, "page_size")["value"] is None
    assert models["chart_type"] == ["table", "bar", "pie", "topN"]
    model_counts = sources["cmdb/query_cmdb_model_counts"]
    assert model_counts["chart_type"] == ["single"]
    assert [field["key"] for field in model_counts["field_schema"]] == ["model_count"]
    assert "不支持分页" in model_counts["desc"]
    assert "page" not in {param["name"] for param in model_counts["params"]}
    assert "analysis_mode" not in {param["name"] for param in model_counts["params"]}
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
    assert "group_by" not in alert_names
    value_field = next(field for field in alerts["field_schema"] if field["key"] == "value")
    assert value_field["title"] == "告警值"
    content = next(field for field in alerts["field_schema"] if field["key"] == "content")
    assert content["title"] == "告警名称"
    object_name = next(field for field in alerts["field_schema"] if field["key"] == "monitor_object_name")
    assert "展示名" in object_name["description"]
    assert "id" in {field["key"] for field in alerts["field_schema"]}
    assert "monitor_object_id" in {field["key"] for field in alerts["field_schema"]}
    assert "updated_at" not in {field["key"] for field in alerts["field_schema"]}
    assert "status" in {field["key"] for field in center["field_schema"]}

    center_keys = {field["key"] for field in center["field_schema"]}
    assert {"alert_id", "event_id", "source_name", "source_id"} <= center_keys
    instances = sources["monitor/query_monitor_instances"]
    assert "status" in {field["key"] for field in instances["field_schema"]}
    assert "instance_count" not in {field["key"] for field in instances["field_schema"]}
    assert "cmdb_bind_status" not in {field["key"] for field in instances["field_schema"]}
    assert "unit" not in {field["key"] for field in instances["field_schema"]}
    instance_query = sources["cmdb/query_cmdb_instances"]
    one_hop = sources["cmdb/query_cmdb_one_hop"]
    metric = sources["monitor/query_monitor_metric"]
    models = sources["cmdb/query_cmdb_models"]

    def field_keys(source):
        return [field["key"] for field in source["field_schema"]]

    assert field_keys(instance_query) == ["inst_uuid", "inst_name"]
    assert instance_query["chart_type"] == ["table"]
    instance_value = sources["cmdb/query_cmdb_instance_value"]
    assert instance_value["chart_type"] == ["single"]
    assert field_keys(instance_value) == ["value"]
    assert "page" not in {param["name"] for param in instance_value["params"]}
    assert "group_by" not in {param["name"] for param in instance_value["params"]}
    assert _param(instance_value, "aggregate_field")["desc"]
    assert _param(instance_value, "aggregate_op")["desc"]
    instance_distribution = sources["cmdb/query_cmdb_instance_distribution"]
    assert instance_distribution["chart_type"] == ["bar", "pie", "topN"]
    assert field_keys(instance_distribution) == ["instance_count"]
    assert "page" not in {param["name"] for param in instance_distribution["params"]}
    assert field_keys(one_hop) == [
        "start_uuid",
        "start_name",
        "end_uuid",
        "end_name",
        "asst_name",
        "model_asst_id",
    ]
    assert one_hop["chart_type"] == ["table"]
    one_hop_counts = sources["cmdb/query_cmdb_one_hop_counts"]
    assert one_hop_counts["chart_type"] == ["single"]
    assert field_keys(one_hop_counts) == ["relation_count"]
    assert "page" not in {param["name"] for param in one_hop_counts["params"]}
    one_hop_rank = sources["cmdb/query_cmdb_one_hop_distribution"]
    assert one_hop_rank["chart_type"] == ["topN"]
    assert field_keys(one_hop_rank) == ["start_name", "start_uuid", "relation_count"]
    assert "page" not in {param["name"] for param in one_hop_rank["params"]}
    assert "analysis_mode" not in {param["name"] for param in one_hop["params"]}
    assert "order" not in {param["name"] for param in one_hop["params"]}
    assert "direction" not in {param["name"] for param in one_hop["params"]}
    assert "relation_count" not in {field["key"] for field in one_hop["field_schema"]}
    assert "start_count" not in {field["key"] for field in one_hop["field_schema"]}
    assert "status" not in field_keys(instance_query)
    assert field_keys(instances) == [
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
    assert "order_by" not in {param["name"] for param in instances["params"]}
    assert "order_dir" not in {param["name"] for param in instances["params"]}
    for rest_api in (
        "monitor/query_monitor_instances",
        "monitor/query_monitor_metric",
        "monitor/query_monitor_alerts",
        "monitor/query_monitor_alert_counts",
        "monitor/query_monitor_alert_distribution",
    ):
        options = _param(sources[rest_api], "monitor_object_id")["inputConfig"]["optionsSource"]
        assert options["valueField"] == "id"
        assert options["labelField"] == "display_name"
    assert "value" in field_keys(alerts)
    assert "id" in field_keys(alerts)
    assert "alert_count" not in field_keys(alerts)
    assert "name" not in field_keys(alerts)
    counts = sources["monitor/query_monitor_alert_counts"]
    assert field_keys(counts) == ["alert_count"]
    assert counts["chart_type"] == ["single"]
    assert alerts["chart_type"] == ["table"]
    distribution = sources["monitor/query_monitor_alert_distribution"]
    assert distribution["chart_type"] == ["pie", "bar"]
    assert field_keys(distribution) == ["group_value", "alert_count"]
    assert _param(distribution, "group_by")["required"] is True
    assert _option_values(_param(distribution, "group_by")) == {"level", "monitor_object_id", "alert_type"}
    assert "status" not in _option_values(_param(distribution, "group_by"))
    assert "analysis_mode" not in {param["name"] for param in distribution["params"]}
    assert "page" not in {param["name"] for param in distribution["params"]}
    assert "status" in field_keys(center)
    assert "record_count" not in field_keys(center)
    assert "record_count" not in _option_values(_param(center, "order_by"))
    assert _option_values(_param(sources["alert/query_alert_center_distribution"], "order_by")) == {
        "level",
        "status",
        "source_name",
        "record_count",
    }
    center_counts = sources["alert/query_alert_center_counts"]
    assert center_counts["chart_type"] == ["single"]
    assert field_keys(center_counts) == ["record_count"]
    assert "page" not in {param["name"] for param in center_counts["params"]}
    assert "group_by" not in {param["name"] for param in center_counts["params"]}
    center_distribution = sources["alert/query_alert_center_distribution"]
    assert center_distribution["chart_type"] == ["bar", "pie", "topN"]
    assert field_keys(center_distribution) == ["level", "status", "source_name", "record_count"]
    assert "page" not in {param["name"] for param in center_distribution["params"]}
    assert "unit" not in field_keys(center)
    assert "table" not in {key for field in metric["field_schema"] for key in field}
    assert [field["key"] for field in models["field_schema"]] == [
        "classification_name",
        "model_name",
        "model_id",
        "instance_count",
    ]
    assert "model_count" not in {field["key"] for field in models["field_schema"]}


def test_model_query_resolver_keeps_explicit_values_and_skips_hidden_defaults():
    from apps.operation_analysis.views.datasource_view import _resolve_request_params

    models = _sources()["cmdb/query_cmdb_models"]
    instance = SimpleNamespace(rest_api="cmdb/query_cmdb_models", params=models["params"])
    narrowed = _resolve_request_params(
        instance,
        {"classification_id": "compute"},
    )
    explicit = _resolve_request_params(
        instance,
        {"page": 2, "page_size": 20},
    )
    cleared = _resolve_request_params(
        instance,
        {"page": None, "page_size": ""},
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
    with pytest.raises(ValueError, match="未声明参数"):
        _resolve_request_params(instance, {"analysis_mode": "detail"})
    legacy = SimpleNamespace(
        rest_api="legacy/query",
        params=[
            {"name": "page", "type": "number", "value": 2, "filterType": "params"},
            {"name": "page_size", "type": "number", "value": 15, "filterType": "params"},
        ],
    )
    kept = _resolve_request_params(legacy, {})

    assert narrowed["classification_id"] == "compute"
    assert "page" not in narrowed
    assert "page_size" not in narrowed
    assert explicit["page"] == 2
    assert explicit["page_size"] == 20
    assert cleared["page"] is None
    assert cleared["page_size"] == ""
    assert omitted == {"analysis_mode": "count", "page": None, "page_size": ""}
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

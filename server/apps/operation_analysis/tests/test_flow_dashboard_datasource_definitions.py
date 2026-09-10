import json
from pathlib import Path

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources_by_key():
    return {item.get("key") or f'{item["name"]}::{item["rest_api"]}': item for item in json.loads(SOURCE_API.read_text(encoding="utf-8"))}


def test_flow_datasource_keys_are_unique():
    payload = json.loads(SOURCE_API.read_text(encoding="utf-8"))
    keys = [item.get("key") or f'{item["name"]}::{item["rest_api"]}' for item in payload]
    assert len(keys) == len(set(keys))
    assert "监控实例列表::monitor/get_monitor_instance_list" in keys
    assert "受控指标趋势::monitor/query_metric_series" in keys
    assert "受控指标排行::monitor/query_metric_series" in keys


def test_monitor_instance_list_is_option_only_source():
    source = _sources_by_key()["监控实例列表::monitor/get_monitor_instance_list"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} >= {"instance_id", "display_name", "object_name", "enabled_protocols"}


def test_metric_series_range_source_binds_instance_ids_and_metric_switch():
    source = _sources_by_key()["受控指标趋势::monitor/query_metric_series"]
    assert source["rest_api"] == "monitor/query_metric_series"
    assert source["chart_type"] == ["line", "bar"]
    instance_ids = next(item for item in source["params"] if item["name"] == "instance_ids")
    assert instance_ids["type"] == "string"
    assert instance_ids["filterType"] == "filter"
    assert instance_ids["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "monitor/get_monitor_instance_list"
    metric = next(item for item in source["params"] if item["name"] == "metric")
    assert metric["inputConfig"]["componentSwitch"] is True
    assert {item["value"] for item in metric["inputConfig"]["optionsSource"]["staticItems"]} >= {
        "device_flow_bytes_rate",
        "device_flow_packets_rate",
        "device_flow_protocol_bytes_rate",
    }
    mode = next(item for item in source["params"] if item["name"] == "mode")
    assert mode["value"] == "range"
    assert mode["filterType"] == "fixed"
    time_param = next(item for item in source["params"] if item["name"] == "time")
    assert time_param["type"] == "timeRange"
    assert time_param["filterType"] == "filter"


def test_metric_series_instant_source_supports_rank_charts():
    source = _sources_by_key()["受控指标排行::monitor/query_metric_series"]
    assert source["rest_api"] == "monitor/query_metric_series"
    assert set(source["chart_type"]) >= {"topN", "table", "single", "pie", "nodeGraph"}
    mode = next(item for item in source["params"] if item["name"] == "mode")
    assert mode["value"] == "instant"
    assert mode["filterType"] == "fixed"
    metric = next(item for item in source["params"] if item["name"] == "metric")
    assert {item["value"] for item in metric["inputConfig"]["optionsSource"]["staticItems"]} >= {
        "device_flow_bytes_rate",
        "device_flow_top_src_bytes_rate",
        "device_flow_top_src_ip_port_bytes_rate",
        "device_flow_top_dst_ip_port_bytes_rate",
        "device_flow_top_conversation_bytes_rate",
    }
    assert {field["key"] for field in source["field_schema"]} >= {
        "name",
        "value",
        "src",
        "dst",
        "protocol",
        "dst_port",
    }

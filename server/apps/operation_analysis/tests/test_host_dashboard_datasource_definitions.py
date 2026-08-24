import json
from pathlib import Path

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"


def _sources_by_api():
    return {item["rest_api"]: item for item in json.loads(SOURCE_API.read_text(encoding="utf-8"))}


def test_host_instance_list_is_option_only_source():
    source = _sources_by_api()["monitor/get_host_instance_list"]
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} == {"instance_id", "display_name"}


def test_host_metric_range_binds_instance_ids_and_metric_switch():
    source = _sources_by_api()["monitor/get_host_metric_range"]
    assert source["chart_type"] == ["line", "bar"]
    instance_ids = next(item for item in source["params"] if item["name"] == "instance_ids")
    assert instance_ids["type"] == "stringList"
    assert instance_ids["filterType"] == "filter"
    metric = next(item for item in source["params"] if item["name"] == "metric_type")
    assert metric["inputConfig"]["componentSwitch"] is True
    assert {item["value"] for item in metric["inputConfig"]["optionsSource"]["staticItems"]} >= {
        "cpu",
        "memory",
        "disk",
        "load5",
        "net_in",
        "net_out",
        "disk_io",
        "disk_write_latency",
        "disk_read_rate",
        "disk_write_rate",
        "processes_blocked",
        "processes_zombies",
    }
    time_param = next(item for item in source["params"] if item["name"] == "time")
    assert time_param["type"] == "timeRange"
    assert time_param["filterType"] == "filter"


def test_host_resource_snapshot_has_no_health_fields():
    source = _sources_by_api()["monitor/get_host_resource_snapshot"]
    field_keys = {field["key"] for field in source["field_schema"]}
    assert field_keys == {
        "host_count",
        "avg_cpu",
        "avg_memory",
        "avg_disk",
        "max_cpu",
        "max_cpu_host",
        "max_memory",
        "max_memory_host",
    }
    assert "healthy" not in field_keys
    assert "unhealthy" not in field_keys
    instance_ids = next(item for item in source["params"] if item["name"] == "instance_ids")
    assert instance_ids["type"] == "stringList"
    assert instance_ids["filterType"] == "filter"

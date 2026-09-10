import json
from pathlib import Path

SOURCE_API = Path(__file__).parents[1] / "support-files" / "source_api.json"

DEFAULT_THRESHOLDS = {
    "login_min": -1,
    "login_max": 2,
    "packets_recv_max_min": -1,
    "packets_recv_max_max": 200,
    "packets_recv_avg_min": -1,
    "packets_recv_avg_max": 50,
    "cpu_avg_min": -1,
    "cpu_avg_max": 8,
    "cpu_max_min": -1,
    "cpu_max_max": 20,
    "mem_avg_min": -1,
    "mem_avg_max": 25,
    "mem_max_min": -1,
    "mem_max_max": 40,
    "io_max_min": -1,
    "io_max_max": 10,
}

ZOMBIE_TABLE_FIELDS = {
    "biz_name",
    "host_name",
    "os_type_label",
    "ip",
    "packets_recv_max",
    "packets_recv_avg",
    "login_count",
    "login_status",
    "cpu_max",
    "cpu_avg",
    "mem_max",
    "mem_avg",
    "io_max",
    "zombie_whitelist",
    "inst_uuid",
    "monitor_id",
}


def _payload():
    return json.loads(SOURCE_API.read_text(encoding="utf-8"))


def _sources_by_key():
    return {item.get("key") or f'{item["name"]}::{item["rest_api"]}': item for item in _payload()}


def test_zombie_datasource_keys_are_unique():
    keys = [item.get("key") or f'{item["name"]}::{item["rest_api"]}' for item in _payload()]
    assert len(keys) == len(set(keys))
    assert "已监控CMDB主机::cmdb/list_monitored_hosts" in keys
    assert "应用系统::cmdb/list_application_systems" in keys
    assert "僵尸机查询::monitor/get_zombie_host_report" in keys


def test_list_monitored_hosts_is_option_only_source():
    source = _sources_by_key()["已监控CMDB主机::cmdb/list_monitored_hosts"]
    assert source["rest_api"] == "cmdb/list_monitored_hosts"
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} >= {"inst_uuid", "display_name"}


def test_list_application_systems_is_option_only_source():
    source = _sources_by_key()["应用系统::cmdb/list_application_systems"]
    assert source["rest_api"] == "cmdb/list_application_systems"
    assert source["chart_type"] == []
    assert source["params"] == []
    assert {field["key"] for field in source["field_schema"]} >= {"inst_uuid", "display_name"}


def test_zombie_host_report_source_binds_cmdb_systems_time_and_thresholds():
    source = _sources_by_key()["僵尸机查询::monitor/get_zombie_host_report"]
    assert source["rest_api"] == "monitor/get_zombie_host_report"
    assert source["chart_type"] == ["table"]

    by_name = {item["name"]: item for item in source["params"]}

    system_uuids = by_name["system_uuids"]
    assert system_uuids["type"] == "string"
    assert system_uuids["filterType"] == "filter"
    assert system_uuids["inputConfig"]["multiple"] is True
    assert system_uuids["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "cmdb/list_application_systems"
    assert system_uuids["inputConfig"]["optionsSource"]["valueField"] == "inst_uuid"
    assert system_uuids["inputConfig"]["optionsSource"]["labelField"] == "display_name"

    time_param = by_name["time"]
    assert time_param["type"] == "timeRange"
    assert time_param["value"] == 10080
    assert time_param["filterType"] == "filter"

    os_type = by_name["os_type"]
    assert os_type["type"] == "string"
    assert os_type["filterType"] == "filter"

    whitelist = by_name["zombie_whitelist"]
    assert whitelist["type"] == "string"
    assert whitelist["filterType"] == "filter"

    assert by_name["page"]["filterType"] == "params"
    assert by_name["page_size"]["filterType"] == "params"

    for name, value in DEFAULT_THRESHOLDS.items():
        param = by_name[name]
        assert param["type"] == "number"
        assert param["filterType"] == "filter"
        assert param["value"] == value

    assert {field["key"] for field in source["field_schema"]} >= ZOMBIE_TABLE_FIELDS

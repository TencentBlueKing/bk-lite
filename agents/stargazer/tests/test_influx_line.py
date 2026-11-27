"""配置采集和监控共用的 Influx 行必须可被严格解析，丢行时不记下字段原文。"""

import logging

from core.collection.contracts import StructuredMetricsPayload
from core.collection.host_proc_influx import host_proc_line
from core.collection.influx_line import encode_influx_line, parse_influx_line
from influxdb_client import Point, WritePrecision
from plugins.base_utils import convert_to_prometheus_format
from tasks.utils.nats_helper import convert_prometheus_to_influx, convert_structured_metrics_to_influx

_PARAMS = {
    "host": "10.0.0.8",
    "plugin_name": "snmp_facts",
    "_publish_timestamp_ms": 1700000000123,
    "tags": {
        "instance_id": "sw-1",
        "collect_type": "cmdb",
        "instance_type": "network",
        "config_type": "snmp",
    },
}


def _point_line(measurement, tags, field_name, field_value, timestamp_ns):
    point = Point(measurement)
    for key, value in tags.items():
        point.tag(key, value)
    if isinstance(field_value, float):
        point.field(field_name, field_value)
    else:
        point.field(field_name, field_value)
    point.time(timestamp_ns, WritePrecision.NS)
    return point.to_line_protocol()


def test_clean_line_matches_point_and_both_collection_paths(monkeypatch):
    monkeypatch.setattr("plugins.base_utils.time.time", lambda: 1700000000.123)
    monkeypatch.setattr("tasks.utils.nats_helper.time.time", lambda: 1700000000.123)
    data = {"network_interfaces": [{"index": "1", "description": "GigabitEthernet0/1", "alias": "uplink"}]}
    structured = convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), _PARAMS)
    prometheus = convert_prometheus_to_influx(convert_to_prometheus_format(data), _PARAMS)
    assert structured == prometheus
    parsed = parse_influx_line(structured[0])
    assert parsed is not None
    assert parsed[0] == "network_interfaces_info"
    assert parsed[1]["description"] == "GigabitEthernet0/1"
    assert parsed[2] == "gauge=1i"
    direct = encode_influx_line(
        "network_interfaces_info",
        {
            "description": "GigabitEthernet0/1",
            "index": "1",
            "alias": "uplink",
        },
        "gauge",
        1,
        1700000000123000000,
    )
    assert direct == _point_line(
        "network_interfaces_info",
        {
            "description": "GigabitEthernet0/1",
            "index": "1",
            "alias": "uplink",
        },
        "gauge",
        1,
        1700000000123000000,
    )


def test_dirty_interface_is_kept_and_sibling_ip_survives(monkeypatch, caplog):
    monkeypatch.setattr("plugins.base_utils.time.time", lambda: 1700000000.123)
    monkeypatch.setattr("tasks.utils.nats_helper.time.time", lambda: 1700000000.123)
    description = "GigabitEthernet0/1\x00"
    alias = "C:\\Program Files\\switch\\"
    data = {
        "ip": [{"ip_addr": "10.1.0.8"}],
        "network_interfaces": [{"index": "2", "description": description, "alias": alias}],
    }
    with caplog.at_level(logging.WARNING):
        structured = convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), _PARAMS)
        prometheus = convert_prometheus_to_influx(convert_to_prometheus_format(data), _PARAMS)
    assert not caplog.records
    assert [line.split(",", 1)[0] for line in structured] == ["ip_info", "network_interfaces_info"]
    assert structured == prometheus
    for line in structured:
        parsed = parse_influx_line(line)
        assert parsed is not None
        assert "\x00" not in line
    interface = parse_influx_line(structured[1])
    assert interface[1]["description"] == "GigabitEthernet0/1"
    assert interface[1]["alias"] == "C:\\Program Files\\switch\\"
    assert interface[1]["index"] == "2"
    assert "ip_addr" not in interface[1]
    assert parse_influx_line(structured[0])[1]["ip_addr"] == "10.1.0.8"


def test_monitor_numeric_fields_and_windows_path_round_trip():
    text = "\n".join(
        [
            'disk_free{path="C:\\\\Program Files",instance_id="h1"} 12.5 1700000000123',
            "# TYPE host_cpu_core_count gauge",
            'host_cpu_core_count{instance_id="h1"} 4 1700000000123',
            "",
        ]
    )
    lines = convert_prometheus_to_influx(text, {"monitor_type": "host", "host": "10.0.0.8"})
    disk = parse_influx_line(lines[0])
    cpu = parse_influx_line(lines[1])
    assert disk is not None and cpu is not None
    assert disk[1]["path"] == "C:\\Program Files"
    assert disk[2] == "value=12.5"
    assert cpu[2] == "gauge=4i"
    assert lines[0].startswith("disk_free,")
    assert not lines[0].startswith(" ")


def test_invalid_measurement_is_dropped_without_logging_the_payload(monkeypatch, caplog):
    sentinel = "PAYLOAD_SENTINEL_ifdescr"
    test_logger = logging.getLogger("test.influx.line.drop")
    monkeypatch.setattr("core.collection.influx_line.logger", test_logger)
    prometheus = "\n".join(
        [
            'ok_metric{instance_id="keep"} 1 1700000000123',
            f'bad\x00metric{{instance_id="sw-1",note="{sentinel}"}} 1 1700000000123',
            "",
        ]
    )
    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        lines = convert_prometheus_to_influx(prometheus, {"host": "10.0.0.1", "tags": {"instance_id": "sw-1"}})

    assert len(lines) == 1
    assert lines[0].startswith("ok_metric,")
    assert sentinel not in lines[0]
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].msg == "event=influx_line_dropped measurement=%s reason=%s instance_id=%s"
    assert warnings[0].args[1] == "invalid_measurement"
    assert warnings[0].args[2] == "sw-1"
    rendered = warnings[0].getMessage()
    assert sentinel not in rendered
    assert "\x00" not in rendered
    assert "sw-1" in rendered


def test_invalid_process_is_debug_and_omits_command_text(monkeypatch, caplog):
    sentinel = "PAYLOAD_SENTINEL_cmdline"
    test_logger = logging.getLogger("test.influx.line.proc")
    monkeypatch.setattr("core.collection.influx_line.logger", test_logger)
    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        line = host_proc_line(
            {"pid": "abc", "name": "sshd", "arg": sentinel, "instance_id": "host-1"},
            1700000000123000000,
        )

    assert line is None
    debug_records = [record for record in caplog.records if record.levelno == logging.DEBUG]
    assert len(debug_records) == 1
    assert debug_records[0].msg == "event=influx_line_dropped measurement=%s reason=%s instance_id=%s"
    assert debug_records[0].args == ("host_proc_usage_info", "invalid_process", "host-1")
    rendered = debug_records[0].getMessage()
    assert sentinel not in rendered
    assert "sshd" not in rendered

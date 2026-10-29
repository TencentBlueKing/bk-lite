"""主机进程采集必须写成严格的 Influx 行协议。

进程参数里的反斜杠、换行、空字节会让官方 Point 打出非法 tag。
Telegraf 照单收下后，同一 instance 上的主机监控查询会失败或超时。
"""

import time

from core.collection.contracts import StructuredMetricsPayload
from plugins.base_utils import convert_to_prometheus_format
from tasks.utils.nats_helper import convert_prometheus_to_influx, convert_structured_metrics_to_influx

_ESCAPES = {" ": " ", ",": ",", "=": "=", "\\": "\\"}


def _read_escaped(line, index, stops):
    chars = []
    while index < len(line):
        char = line[index]
        if char == "\\":
            if index + 1 >= len(line) or line[index + 1] not in _ESCAPES:
                raise AssertionError(f"invalid escape at {index}: {line!r}")
            chars.append(_ESCAPES[line[index + 1]])
            index += 2
            continue
        if char in stops or char < " " or char == "\x7f":
            if char in stops:
                break
            raise AssertionError(f"control char in line: {line!r}")
        chars.append(char)
        index += 1
    return "".join(chars), index


def parse_strict_influx(line):
    assert "\n" not in line and "\r" not in line and "\x00" not in line
    measurement, index = _read_escaped(line, 0, {",", " "})
    tags = {}
    if index < len(line) and line[index] == ",":
        index += 1
        while index < len(line) and line[index] != " ":
            key, index = _read_escaped(line, index, {"=", ",", " "})
            assert line[index] == "="
            index += 1
            value, index = _read_escaped(line, index, {",", " "})
            assert key and key not in tags
            tags[key] = value
            if index < len(line) and line[index] == ",":
                index += 1
    assert line[index] == " "
    field_time = line[index + 1 :]
    fields, _, timestamp = field_time.rpartition(" ")
    assert fields == "gauge=1i"
    assert timestamp.isdigit()
    return measurement, tags


def _payload(proc):
    return {
        "host": [{"host": "10.0.0.8", "ip_addr": "10.0.0.8"}],
        "host_proc_usage": [proc],
    }


def _params():
    return {
        "host": "10.0.0.8",
        "_publish_timestamp_ms": 1700000000123,
        "tags": {
            "instance_id": "host-8",
            "collect_type": "cmdb",
            "instance_type": "os",
            "config_type": "host",
        },
    }


def _lines(data):
    params = _params()
    structured = convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), params)
    prometheus = convert_prometheus_to_influx(convert_to_prometheus_format(data), params)
    return structured, prometheus


def test_process_path_and_controls_stay_strict_line_protocol(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1700000000.123)
    arg = "C:\\Program Files\\app\\bin\\ -Dfoo=bar,x\r\nnext\x00\x01\u2028tail"
    structured, prometheus = _lines(
        _payload(
            {
                "pid": "4242",
                "name": "java",
                "arg": arg,
                "exe": "C:\\app\\bin\\java",
                "cwd": "C:\\app",
                "ports": "8080,8443",
            }
        )
    )

    assert [line.split(",", 1)[0] for line in structured] == ["host_info", "host_proc_usage_info"]
    assert structured[0] == prometheus[0]
    proc_line = structured[1]
    assert proc_line == prometheus[1]
    measurement, tags = parse_strict_influx(proc_line)
    assert measurement == "host_proc_usage_info"
    assert tags["arg"] == "C:\\Program Files\\app\\bin\\ -Dfoo=bar,x  next tail"
    assert tags["exe"] == "C:\\app\\bin\\java"
    assert tags["ports"] == "8080,8443"
    assert tags["pid"] == "4242"
    assert tags["instance_id"] == "host-8"
    assert "\x00" not in proc_line
    assert "\u2028" not in proc_line


def test_plain_process_arg_round_trips(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1700000000.123)
    structured, prometheus = _lines(_payload({"pid": "7", "name": "nginx", "arg": "nginx -g daemon off;"}))
    assert structured[1] == prometheus[1]
    _, tags = parse_strict_influx(structured[1])
    assert tags["arg"] == "nginx -g daemon off;"
    assert tags["name"] == "nginx"


def test_invalid_process_is_dropped_without_dropping_host(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1700000000.123)
    structured, prometheus = _lines(_payload({"pid": "not-a-pid", "name": "java", "arg": "C:\\Windows\\System32\\cmd.exe"}))
    assert len(structured) == 1
    assert structured == prometheus
    assert structured[0].startswith("host_info,")
    assert "cmd.exe" not in structured[0]


def test_bad_process_timestamp_does_not_drop_host_info():
    params = _params()
    metrics = (
        "# TYPE host_info gauge\n"
        'host_info{host="10.0.0.8",model_id="host"} 1 1700000000123\n'
        "# TYPE host_proc_usage_info gauge\n"
        'host_proc_usage_info{pid="4242",name="java",arg="C:\\\\Windows\\\\app",model_id="host_proc_usage"} '
        "1 not-a-timestamp\n"
    )
    lines = convert_prometheus_to_influx(metrics, params)
    assert len(lines) == 1
    assert lines[0].startswith("host_info,")
    assert "host_proc_usage_info" not in lines[0]
    assert "Windows" not in lines[0]

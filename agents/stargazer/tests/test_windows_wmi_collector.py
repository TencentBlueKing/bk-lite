import sys
from pathlib import Path
import logging

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

from tasks.collectors.host_wmi.errors import WmiError, classify_wmi_error
from tasks.collectors.host_wmi.client import WmiClient
from tasks.collectors.host_wmi.metrics import wmi_results_to_prometheus
from tasks.collectors.host_wmi.modules import resolve_modules
from tasks.collectors.host_wmi_collector import WindowsWmiCollector
from tasks.utils.nats_helper import convert_prometheus_to_influx


def test_resolve_modules_accepts_comma_separated_values():
    assert resolve_modules("cpu, mem,invalid,disk") == ["cpu", "mem", "disk"]


def test_resolve_modules_accepts_arrays_and_defaults_when_empty():
    assert resolve_modules(["net", "processes", "bad"]) == ["net", "processes"]
    assert resolve_modules("bad,unknown") == ["cpu", "mem", "disk", "net"]


def test_classify_wmi_error_normalizes_common_failures():
    assert classify_wmi_error(PermissionError("access denied")) == "dcom_access_denied"
    assert classify_wmi_error(TimeoutError("timed out")) == "query_timeout"
    assert classify_wmi_error(WmiError("bad namespace", "namespace_not_found")) == "namespace_not_found"


def test_wmi_results_to_prometheus_emits_host_metrics():
    output = wmi_results_to_prometheus(
        {
            "cpu": {"usage_percent": 12.5, "core_count": 4},
            "mem": {
                "total_bytes": 8589934592,
                "available_bytes": 4294967296,
                "used_bytes": 4294967296,
                "used_percent": 50.0,
            },
            "disk": [
                {
                    "device": "C:",
                    "total_bytes": 1000,
                    "free_bytes": 250,
                    "used_bytes": 750,
                    "used_percent": 75.0,
                }
            ],
        },
        {
            "instance_id": "region_os_10.0.0.8",
            "instance_type": "os",
            "collect_type": "http",
            "config_type": "windows_wmi",
        },
        host="10.0.0.8",
        timestamp=1700000000000,
    )

    base = 'instance_id="region_os_10.0.0.8",instance_type="os",collect_type="http",config_type="windows_wmi",host="10.0.0.8"'
    assert f"host_cpu_usage_percent_gauge{{{base}}} 12.5 1700000000000" in output
    assert f"host_cpu_core_count_gauge{{{base}}} 4 1700000000000" in output
    assert f"host_mem_used_percent_gauge{{{base}}} 50 1700000000000" in output
    assert f'host_disk_used_percent_gauge{{{base},device="C:"}} 75 1700000000000' in output


def test_wmi_prometheus_metrics_convert_without_leading_measurement_space():
    prometheus = wmi_results_to_prometheus(
        {
            "cpu": {"usage_percent": 12.5, "core_count": 4},
        },
        {
            "instance_id": "10.0.0.8",
            "instance_type": "os",
            "collect_type": "http",
            "config_type": "windows_wmi",
        },
        host="10.0.0.8",
        timestamp=1700000000000,
    )

    lines = convert_prometheus_to_influx(
        prometheus,
        {
            "monitor_type": "windows_wmi",
            "host": "10.0.0.8",
            "tags": {
                "instance_id": "('10.0.0.8',)",
                "instance_type": "os",
                "collect_type": "http",
                "config_type": "windows_wmi",
            },
        },
    )

    assert lines[0].startswith("host_cpu_usage_percent_gauge,")
    assert not lines[0].startswith(" ")
    assert "instance_id=('10.0.0.8'\\,)" in lines[0]
    assert "value=12.5" in lines[0]


class FakeWmiClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def connect(self):
        return None

    def close(self):
        return None

    def query_class(self, class_name):
        if class_name == "Win32_Processor":
            return [{"LoadPercentage": 25, "NumberOfLogicalProcessors": 8}]
        if class_name == "Win32_OperatingSystem":
            return [{"TotalVisibleMemorySize": 1000, "FreePhysicalMemory": 250}]
        return []

    def query(self, query):
        if "Win32_LogicalDisk" in query:
            return [{"DeviceID": "C:", "Size": 1000, "FreeSpace": 400}]
        return []


@pytest.mark.asyncio
async def test_windows_wmi_collector_collects_selected_modules(monkeypatch):
    monkeypatch.setattr(
        "tasks.collectors.host_wmi_collector.WmiClient",
        FakeWmiClient,
    )
    collector = WindowsWmiCollector(
        {
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "password": "secret",
            "namespace": "root\\cimv2",
            "metrics_modules": "cpu,mem,disk",
            "timeout": 30,
            "tags": {"instance_id": "region_os_10.0.0.8", "instance_type": "os"},
        }
    )

    output = await collector.collect()

    assert "host_cpu_usage_percent_gauge" in output
    assert "host_mem_used_percent_gauge" in output
    assert "host_disk_used_percent_gauge" in output


@pytest.mark.asyncio
async def test_windows_wmi_collector_logs_module_failure_and_continues(monkeypatch, caplog):
    class FailingDiskClient(FakeWmiClient):
        def query(self, query):
            raise RuntimeError("class missing")

    monkeypatch.setattr(
        "tasks.collectors.host_wmi_collector.WmiClient",
        FailingDiskClient,
    )
    collector = WindowsWmiCollector(
        {
            "host": "10.0.0.8",
            "username": "EXAMPLE\\monitor",
            "password": "secret",
            "metrics_modules": "cpu,disk",
            "tags": {"instance_id": "region_os_10.0.0.8", "instance_type": "os"},
        }
    )

    with caplog.at_level(logging.WARNING):
        output = await collector.collect()

    assert "host_cpu_usage_percent_gauge" in output
    assert "host_disk_used_percent_gauge" not in output
    assert "event=wmi_module_failed" in caplog.text
    assert "module=disk" in caplog.text


def test_wmi_client_reports_missing_dependency(monkeypatch):
    client = WmiClient(
        host="10.0.0.8",
        username="EXAMPLE\\monitor",
        password="secret",
        namespace="root\\cimv2",
        timeout=30,
    )

    monkeypatch.setattr(client, "_load_impacket", lambda: (_ for _ in ()).throw(ImportError("missing")))

    try:
        client.connect()
    except WmiError as error:
        assert error.error_type == "unknown"
        assert "impacket" in str(error).lower()
    else:
        raise AssertionError("expected WmiError")


def test_wmi_client_parses_domain_username():
    client = WmiClient(
        host="10.0.0.8",
        username="EXAMPLE\\monitor",
        password="secret",
    )

    assert client._split_username() == ("EXAMPLE", "monitor")


def test_wmi_client_normalizes_wmi_property_rows():
    rows = WmiClient._normalize_rows(
        [
            {
                "Name": {"value": "CPU0"},
                "LoadPercentage": {"value": 12},
                "Ignored": {"value": None},
            }
        ]
    )

    assert rows == [{"Name": "CPU0", "LoadPercentage": 12, "Ignored": None}]

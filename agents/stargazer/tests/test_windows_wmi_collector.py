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
from tasks.collectors.host_wmi import modules as wmi_modules
from tasks.collectors.host_wmi.modules import resolve_modules
from tasks.collectors.host_wmi_collector import WindowsWmiCollector
from tasks.utils.nats_helper import convert_prometheus_to_influx


def test_resolve_modules_accepts_comma_separated_values():
    assert resolve_modules("cpu, mem,invalid,disk") == ["cpu", "mem", "disk"]


def test_resolve_modules_accepts_arrays_and_defaults_when_empty():
    assert resolve_modules(["net", "processes", "bad"]) == ["net", "processes"]
    assert resolve_modules("bad,unknown") == [
        "cpu",
        "mem",
        "disk",
        "diskio",
        "net",
        "processes",
        "system",
    ]


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
                    "path": "C:",
                    "fstype": "NTFS",
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
    assert f'host_disk_used_percent_gauge{{{base},device="C:",path="C:",fstype="NTFS"}} 75 1700000000000' in output


def test_wmi_disk_metrics_filter_fstype_and_emit_path_labels():
    output = wmi_results_to_prometheus(
        {
            "disk": [
                {"device": "C:", "path": "C:", "fstype": "NTFS", "total_bytes": 1000, "free_bytes": 250, "used_bytes": 750, "used_percent": 75},
                {"device": "E:", "path": "E:", "fstype": "FAT32", "total_bytes": 1000, "free_bytes": 250, "used_bytes": 750, "used_percent": 75},
            ]
        },
        {"instance_id": "region_os_10.0.0.8"},
        host="10.0.0.8",
        timestamp=1700000000000,
        disk_include_fstypes="NTFS,FAT32",
        disk_exclude_fstypes="FAT32",
    )

    assert 'device="C:",path="C:",fstype="NTFS"' in output
    assert 'device="E:"' not in output


def test_wmi_disk_module_exposes_filesystem_as_fstype():
    class DiskClient:
        def query(self, _query):
            return [{"DeviceID": "C:", "FileSystem": "NTFS", "Size": 1000, "FreeSpace": 250}]

    disks = wmi_modules.DiskModule().collect(DiskClient())

    assert disks == [
        {"device": "C:", "path": "C:", "fstype": "NTFS", "total_bytes": 1000, "free_bytes": 250, "used_bytes": 750, "used_percent": 75.0}
    ]


def test_wmi_modules_collect_telegraf_aligned_host_metrics():
    class ExtendedFakeWmiClient(FakeWmiClient):
        def query_class(self, class_name):
            if class_name == "Win32_PerfRawData_Tcpip_NetworkInterface":
                return [
                    {
                        "Name": "Ethernet0",
                        "BytesReceivedPersec": 1000,
                        "BytesSentPersec": 2000,
                        "PacketsReceivedPersec": 10,
                        "PacketsSentPersec": 20,
                        "PacketsReceivedErrors": 1,
                        "PacketsOutboundErrors": 2,
                        "PacketsReceivedDiscarded": 3,
                        "PacketsOutboundDiscarded": 4,
                    }
                ]
            if class_name == "Win32_PerfRawData_PerfDisk_PhysicalDisk":
                return [
                    {
                        "Name": "0 C:",
                        "DiskReadsPersec": 5,
                        "DiskWritesPersec": 6,
                        "DiskReadBytesPersec": 700,
                        "DiskWriteBytesPersec": 800,
                        "PercentDiskTime": 9,
                    }
                ]
            if class_name == "Win32_Process":
                return [{"ProcessId": 1}, {"ProcessId": 2}]
            if class_name == "Win32_OperatingSystem":
                return [{"LastBootUpTime": "20240601000000.000000+480"}]
            return super().query_class(class_name)

    client = ExtendedFakeWmiClient()

    for class_name in ("NetModule", "DiskIOModule", "ProcessesModule", "SystemModule"):
        assert hasattr(wmi_modules, class_name)

    assert wmi_modules.NetModule().collect(client) == [
        {
            "interface": "Ethernet0",
            "rx_bytes": 1000,
            "tx_bytes": 2000,
            "rx_packets": 10,
            "tx_packets": 20,
            "rx_errors": 1,
            "tx_errors": 2,
            "rx_drops": 3,
            "tx_drops": 4,
        }
    ]
    assert wmi_modules.DiskIOModule().collect(client) == [
        {
            "name": "0 C:",
            "reads": 5,
            "writes": 6,
            "read_bytes": 700,
            "write_bytes": 800,
            "io_time_ms": 9,
            "read_time_ms": 0,
            "write_time_ms": 0,
        }
    ]
    assert wmi_modules.ProcessesModule().collect(client) == {
        "running": 2,
        "blocked": 0,
        "sleeping": 0,
        "zombies": 0,
    }
    assert "uptime_seconds" in wmi_modules.SystemModule().collect(client)


def test_wmi_results_to_prometheus_emits_telegraf_aligned_network_and_system_metrics():
    output = wmi_results_to_prometheus(
        {
            "net": [
                {
                    "interface": "Ethernet0",
                    "rx_bytes": 1000,
                    "tx_bytes": 2000,
                    "rx_packets": 10,
                    "tx_packets": 20,
                    "rx_errors": 1,
                    "tx_errors": 2,
                    "rx_drops": 3,
                    "tx_drops": 4,
                }
            ],
            "diskio": [
                {
                    "name": "0 C:",
                    "reads": 5,
                    "writes": 6,
                    "read_bytes": 700,
                    "write_bytes": 800,
                    "io_time_ms": 9,
                    "read_time_ms": 0,
                    "write_time_ms": 0,
                }
            ],
            "processes": {"running": 2, "blocked": 0, "sleeping": 0, "zombies": 0},
            "system": {"uptime_seconds": 123, "load1": 0, "load5": 0, "load15": 0},
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
    assert f'net_bytes_recv_gauge{{{base},interface="Ethernet0"}} 1000 1700000000000' in output
    assert f'net_packets_sent_gauge{{{base},interface="Ethernet0"}} 20 1700000000000' in output
    assert f'net_err_in_gauge{{{base},interface="Ethernet0"}} 1 1700000000000' in output
    assert f'diskio_reads_gauge{{{base},name="0 C:"}} 5 1700000000000' in output
    assert f"processes_running_gauge{{{base}}} 2 1700000000000" in output
    assert f"system_uptime_gauge{{{base}}} 123 1700000000000" in output


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

# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from core.collection.plugins import _load_monitor_collector, _resolve_monitor_collector
from tasks.collectors.host_collector import VALID_MODULES
from tasks.collectors.hyperv_collector import HypervCollector
from tasks.collectors.hyperv_metrics import (
    CMDB_HOST_FIELDS,
    CMDB_VM_FIELDS,
    LATENCY_FIELD_NAMES,
    cmdb_fields_exclude_latency,
    cmdb_payload_from_discover,
    latency_to_ms,
    parse_hyperv_metrics_to_prometheus,
    power_state_value,
)

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
LINUX_SCRIPT_DIRS = [
    STARGAZER_ROOT / "tasks/collectors/scripts/linux",
    STARGAZER_ROOT / "plugins/inputs/host",
]


def test_linux_host_scripts_do_not_contain_hyperv():
    markers = ("Get-VM", "Get-VMHost", "root\\virtualization", "Hyper-V Virtual Storage")
    scanned = 0
    for folder in LINUX_SCRIPT_DIRS:
        for path in folder.rglob("*"):
            if path.suffix.lower() not in {".sh", ".py", ".yml"}:
                continue
            if path.name.endswith(".pyc") or path.name == "hyperv_metrics.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            scanned += 1
            for marker in markers:
                assert marker not in text, f"{path} unexpectedly contains {marker}"
    assert scanned >= 3


def test_host_valid_modules_do_not_include_hyperv():
    assert "hyperv" not in VALID_MODULES
    assert VALID_MODULES == {"cpu", "mem", "disk", "net", "diskio", "processes", "system"}


def test_cmdb_fields_exclude_latency():
    assert not (set(CMDB_HOST_FIELDS) & LATENCY_FIELD_NAMES)
    assert not (set(CMDB_VM_FIELDS) & LATENCY_FIELD_NAMES)
    mixed = list(CMDB_HOST_FIELDS) + ["storage_read_latency", "storage_write_latency"]
    assert cmdb_fields_exclude_latency(mixed) == list(CMDB_HOST_FIELDS)


def test_latency_to_ms_converts_seconds_and_keeps_milliseconds():
    assert latency_to_ms(0.002, "s") == pytest.approx(2.0)
    assert latency_to_ms(3.5, "ms") == pytest.approx(3.5)
    assert latency_to_ms(2_000_000, "ns") == pytest.approx(2.0)


def test_power_state_running_is_one():
    assert power_state_value("Running") == 1
    assert power_state_value("Off") == 0
    assert power_state_value("Paused") == 0


def test_prometheus_latency_uses_disk_dimension_and_milliseconds():
    text = parse_hyperv_metrics_to_prometheus(
        {
            "host": {
                "inst_name": "hv01",
                "resource_id": "hv01",
                "cpu_usage": 10,
                "mem_usage": 40,
                "disks": [{"name": "C:", "read_latency": 0.004, "write_latency": 0.001, "unit": "s"}],
            },
            "vms": [
                {
                    "name": "web01",
                    "resource_id": "vm-1",
                    "cpu_usage": 8,
                    "mem_usage": 30,
                    "power_state": "Running",
                    "disks": [{"name": "web01.vhdx", "read_latency_ms": 5, "write_latency_ms": 7}],
                }
            ],
        },
        {"instance_id": "region_hyperv_10.11.27.30", "host": "10.11.27.30"},
    )
    assert 'storage_read_latency{instance_id="region_hyperv_10.11.27.30"' in text
    assert 'disk="C:"' in text
    assert "storage_read_latency" in text and " 4.0" in text
    assert 'disk="web01.vhdx"' in text
    assert "power_state{" in text and " 1.0" in text
    assert "latency" not in str(cmdb_payload_from_discover({"host": {"inst_name": "hv01"}, "vms": []}))


def test_cmdb_payload_does_not_copy_latency_fields():
    payload = cmdb_payload_from_discover(
        {
            "host": {
                "inst_name": "hv01",
                "resource_id": "hv01",
                "ip_addr": "10.11.27.30",
                "cpu_cores": 8,
                "memory_mb": 16384,
                "hyperv_version": "10.0",
                "storage_read_latency": 9,
            },
            "vms": [
                {
                    "inst_name": "web01",
                    "resource_id": "vm-1",
                    "power_state": "Running",
                    "vcpus": 2,
                    "memory_mb": 2048,
                    "read_latency_ms": 3,
                }
            ],
        }
    )
    host = payload["hyperv_host"][0]
    vm = payload["hyperv_vm"][0]
    assert "storage_read_latency" not in host
    assert "read_latency_ms" not in vm
    assert host["memory"] == 16384
    assert vm["memory"] == 2048
    assert vm["self_host"] == "hv01"


def test_load_monitor_collector_resolves_hyperv():
    assert _load_monitor_collector("hyperv") is HypervCollector


def test_community_hyperv_wins_over_enterprise_factory():
    class EnterpriseHyperv:
        pass

    assert _resolve_monitor_collector("hyperv", {"hyperv": EnterpriseHyperv}) is HypervCollector


def test_hyperv_monitor_plugin_yaml_skips_stargazer_preflight():
    text = (STARGAZER_ROOT / "plugins/inputs/hyperv/plugin.yml").read_text(encoding="utf-8")
    assert "default_executor: protocol" in text
    assert "mode: skip" in text

"""Datastore read/write latency stays on vmware_ds, empty instance only, no /100."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock

from common.cmp.cloud_apis.resource_apis.cw_vmware import Vmware

METRICS = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/metrics.json"

ESXI_DEFAULT = [
    "cpu_usage_average",
    "cpu_usagemhz_average",
    "mem_usage_average",
    "mem_consumed_average",
    "disk_read_average",
    "disk_write_average",
    "net_bytesRx_average",
    "net_bytesTx.average",
    "disk_numberRead_summation",
    "disk_numberWrite_summation",
    "datastore_io_read_latency",
    "datastore_io_write_latency",
    "datastore_iops_read",
    "datastore_iops_write",
    "datastore_throughput_read",
    "datastore_throughput_write",
    "net_usage_average",
    "boot_time",
    "uptime_seconds",
]

VM_DEFAULT = [
    "cpu_usage_average",
    "cpu_usagemhz_average",
    "mem_usage_average",
    "mem_consumed_average",
    "disk_used_average",
    "disk_read_average",
    "disk_write_average",
    "net_bytesRx_average",
    "net_bytesTx.average",
    "disk_numberRead_summation",
    "disk_numberWrite_summation",
    "disk_io_usage",
    "power_state",
    "tools_status",
    "disk_io_read_latency",
    "disk_io_write_latency",
    "snapshot_storage_bytes",
    "oldest_snapshot_age_seconds",
    "snapshot_count",
]


def _driver():
    return Vmware.__new__(Vmware)


def test_datastore_default_metrics_include_aggregate_latency():
    driver = _driver()
    _obj_type, _vim_types, metrics = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_ds"}], None)
    assert "datastore_io_read_latency" in metrics
    assert "datastore_io_write_latency" in metrics
    assert metrics[:3] == ["disk_used_average", "disk_free_average", "store_accessible"]
    batch, special = driver._categorize_metrics(metrics, "datastore")
    assert "datastore.totalReadLatency.average" in batch
    assert "datastore.totalWriteLatency.average" in batch
    assert "datastore_io_read_latency" not in special
    assert "store_accessible" in special


def test_esxi_and_vm_default_metrics_unchanged():
    driver = _driver()
    _, _, esxi = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_esxi"}], None)
    _, _, vm = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_vm"}], None)
    assert esxi == ESXI_DEFAULT
    assert vm == VM_DEFAULT


def test_datastore_latency_keeps_empty_instance_and_drops_named():
    driver = _driver()
    driver._convert_vmware_datetime_to_timestamp = lambda _dt: 1_700_000_000
    counter_name = "datastore.totalReadLatency.average"
    counter_info = {counter_name: 101}
    counter_to_metric = {counter_name: "datastore_io_read_latency"}

    empty = MagicMock()
    empty.id.counterId = 101
    empty.id.instance = ""
    empty.value = [15]

    named = MagicMock()
    named.id.counterId = 101
    named.id.instance = "vm-1"
    named.value = [999]

    entity = MagicMock()
    entity.entity._moId = "datastore-1"
    entity.sampleInfo = [MagicMock()]
    entity.value = [empty, named]

    res = {}
    driver._process_entity_values(entity, "datastore-1", counter_info, counter_to_metric, res)

    series = res["datastore-1"]["datastore_io_read_latency"]
    assert series[0][1] == 15.0
    assert not isinstance(series, dict)
    values = [point[1] for point in series]
    assert 999 not in values
    assert 9.99 not in values


def test_datastore_latency_not_divided_by_100():
    driver = _driver()
    value_info = MagicMock()
    value_info.id.instance = ""
    value_info.value = [250]
    entity = MagicMock()
    entity.value = [value_info]
    entity.entity.name = "ds1"
    res = {}
    driver._add_metric_value("datastore-1", "datastore_io_write_latency", value_info, 0, 1_700_000_000, entity, res)
    assert res["datastore-1"]["datastore_io_write_latency"][0][1] == 250.0


def test_datastore_perf_query_uses_hour_window():
    driver = _driver()
    data = {
        "StartTime": "2026-10-25 11:55:00",
        "EndTime": "2026-10-25 12:00:00",
    }
    driver._prepare_datastore_perf_query(data)
    assert data["interval"] == 300
    start = datetime.datetime.strptime(data["StartTime"], "%Y-%m-%d %H:%M:%S")
    end = datetime.datetime.strptime(data["EndTime"], "%Y-%m-%d %H:%M:%S")
    assert (end - start).total_seconds() >= 3600


def test_datastore_batch_forwards_300s_interval():
    driver = _driver()
    seen = {}

    def fake_batch(counters, interval=20, **kwargs):
        seen["interval"] = interval
        seen["counters"] = counters
        return {"result": False, "message": "skip"}

    driver.monitor_data_batch = fake_batch
    driver._fallback_to_individual_requests = lambda *a, **k: False
    driver._process_batch_monitoring_data(
        ["datastore.totalReadLatency.average"],
        [object()],
        {"interval": 300},
        ["datastore_io_read_latency"],
        None,
        {},
    )
    assert seen["interval"] == 300


def test_vmware_plugin_registers_datastore_latency_gauges():
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    ds = next(obj for obj in metrics["objects"] if obj["name"] == "DataStorage")
    by_name = {item["name"]: item for item in ds["metrics"]}
    for name in ("datastore_io_read_latency_gauge", "datastore_io_write_latency_gauge"):
        item = by_name[name]
        assert item["unit"] == "ms"
        assert 'resource_type=\\"vmware_ds\\"' in item["query"] or 'resource_type="vmware_ds"' in item["query"]
        assert "_gauge{" in item["query"]
    assert by_name["disk_used_average_gauge"]["query"].startswith("disk_used_average_gauge")

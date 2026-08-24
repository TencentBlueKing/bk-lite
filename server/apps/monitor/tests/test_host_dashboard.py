from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.services.host_dashboard import (
    EMPTY_SNAPSHOT,
    HostMetricRangeService,
    build_host_instance_rows,
    build_host_resource_snapshot,
    fold_host_range_series,
    validate_range_metric_type,
)
from apps.monitor.services.host_resource_top import HostCandidate

NOW = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
TS = 1755669600.0


def test_range_metric_type_rejects_unknown():
    validate_range_metric_type("cpu")
    with pytest.raises(ValueError):
        validate_range_metric_type("health")


def test_host_instance_rows_use_display_name_and_sort():
    rows = build_host_instance_rows(
        [
            SimpleNamespace(id="host-b", name="web-2", ip="10.0.0.2"),
            SimpleNamespace(id="host-a", name="web-1", ip="10.0.0.1"),
        ]
    )
    assert rows == [
        {"instance_id": "host-a", "display_name": "web-1 (10.0.0.1)"},
        {"instance_id": "host-b", "display_name": "web-2 (10.0.0.2)"},
    ]


def test_fold_sums_nics_and_maxes_disks_per_host():
    host_meta = {
        "host-a": {"host_name": "web-1", "ip": "10.0.0.1"},
        "host-b": {"host_name": "web-2", "ip": "10.0.0.2"},
    }
    series = [
        {"metric": {"instance_id": "host-a", "interface": "eth0"}, "values": [[TS, "10"], [TS + 60, "12"]]},
        {"metric": {"instance_id": "host-a", "interface": "eth1"}, "values": [[TS, "5"], [TS + 60, "8"]]},
        {"metric": {"instance_id": "host-b", "interface": "eth0"}, "values": [[TS, "3"]]},
        {"metric": {"instance_id": "not-authorized", "interface": "eth0"}, "values": [[TS, "99"]]},
    ]
    summed = fold_host_range_series(series, host_meta, fold="sum")
    assert summed["web-1 (10.0.0.1)"] == [[TS, 15.0], [TS + 60, 20.0]]
    assert summed["web-2 (10.0.0.2)"] == [[TS, 3.0]]

    disk_series = [
        {"metric": {"instance_id": "host-a", "path": "/"}, "values": [[TS, "61"]]},
        {"metric": {"instance_id": "host-a", "path": "/data"}, "values": [[TS, "92"]]},
    ]
    maxed = fold_host_range_series(disk_series, host_meta, fold="max")
    assert maxed["web-1 (10.0.0.1)"] == [[TS, 92.0]]


def test_fold_converts_cpu_idle_and_drops_empty_selection():
    host_meta = {"host-a": {"host_name": "web-1", "ip": "10.0.0.1"}}
    series = [{"metric": {"instance_id": "host-a"}, "values": [[TS, "22.5"]]}]
    folded = fold_host_range_series(
        series,
        host_meta,
        fold="identity",
        transform=lambda value: 100.0 - value,
    )
    assert folded["web-1 (10.0.0.1)"] == [[TS, 77.5]]
    assert fold_host_range_series(series, {}, fold="identity") == {}


def test_range_service_does_not_query_when_no_hosts_selected():
    class FailVM:
        def query_range(self, *args, **kwargs):
            raise AssertionError("empty selection must not query")

    assert (
        HostMetricRangeService(vm_api=FailVM()).run(
            metric_type="cpu",
            time_range=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
            instances=[],
        )
        == {}
    )


def test_range_service_returns_object_keyed_series():
    class FakeVM:
        def query_range(self, query, start, end, step):
            self.args = (query, start, end, step)
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "host-a"}, "values": [[TS, "40"]]},
                    ]
                },
            }

    vm = FakeVM()
    data = HostMetricRangeService(vm_api=vm).run(
        metric_type="memory",
        time_range=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        instances=[SimpleNamespace(id="host-a", name="web-1", ip="10.0.0.1")],
    )
    assert data == {"web-1 (10.0.0.1)": [[TS, 40.0]]}
    assert vm.args[0] == '{__name__="mem_used_percent"}'


def test_snapshot_has_no_health_fields_and_computes_avg_max():
    host_meta = {
        "host-a": {"host_name": "web-1", "ip": "10.0.0.1", "interval": 300},
        "host-b": {"host_name": "web-2", "ip": "10.0.0.2", "interval": 300},
    }
    snapshot = build_host_resource_snapshot(
        host_meta=host_meta,
        cpu_candidates=[
            HostCandidate("host-a", 40, NOW, "cpu"),
            HostCandidate("host-b", 80, NOW, "cpu"),
        ],
        memory_candidates=[
            HostCandidate("host-a", 10, NOW, "memory"),
            HostCandidate("host-b", 30, NOW, "memory"),
        ],
        disk_candidates=[
            HostCandidate("host-a", 70, NOW, "disk", {"mount": "/"}),
            HostCandidate("host-a", 90, NOW, "disk", {"mount": "/data"}),
        ],
        now=NOW,
        host_count=2,
    )
    assert snapshot["host_count"] == 2
    assert snapshot["avg_cpu"] == 60.0
    assert snapshot["max_cpu"] == 80.0
    assert snapshot["max_cpu_host"] == "web-2 (10.0.0.2)"
    assert snapshot["avg_memory"] == 20.0
    assert snapshot["max_memory"] == 30.0
    assert snapshot["avg_disk"] == 90.0
    assert "healthy" not in snapshot
    assert "unhealthy" not in snapshot
    assert set(EMPTY_SNAPSHOT) <= set(snapshot)

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from apps.monitor.services.host_resource_top import (
    SUPPORTED_METRIC_TYPES,
    HostCandidate,
    build_ranked_rows,
    normalize_metric_candidates,
    validate_metric_type,
    HostResourceTopService,
)


NOW = datetime(2026, 7, 21, 6, 0, tzinfo=timezone.utc)


def candidate(instance_id, value, *, sampled_at=None, metric_type="cpu", **labels):
    return HostCandidate(
        instance_id=instance_id,
        value=value,
        sampled_at=sampled_at or NOW,
        metric_type=metric_type,
        labels=labels,
    )


def test_metric_type_accepts_only_cpu_memory_and_disk():
    assert {validate_metric_type(item) for item in SUPPORTED_METRIC_TYPES} == set(SUPPORTED_METRIC_TYPES)

    with pytest.raises(ValueError):
        validate_metric_type("network")


def test_ranked_rows_take_top_ten_and_stable_ties():
    hosts = [candidate(f"host-{index:02d}", 50) for index in range(12)]
    rows = build_ranked_rows(hosts, host_meta={})

    assert len(rows) == 10
    assert [row["rank"] for row in rows] == list(range(1, 11))
    assert [row["instance_id"] for row in rows] == [f"host-{index:02d}" for index in range(10)]


def test_normalize_filters_invalid_values_and_stale_samples():
    raw = [
        candidate("fresh", 80),
        candidate("stale", 99, sampled_at=NOW - timedelta(minutes=11)),
        candidate("nan", float("nan")),
        candidate("out-of-range", 101),
    ]

    normalized = normalize_metric_candidates(
        raw,
        host_meta={"fresh": {"interval": 300}, "stale": {"interval": 300}},
        now=NOW,
    )

    assert [item.instance_id for item in normalized] == ["fresh"]


def test_disk_normalization_keeps_fullest_fresh_filesystem_per_host():
    raw = [
        candidate("host-a", 61, metric_type="disk", mount="/"),
        candidate("host-a", 92, metric_type="disk", mount="/data"),
        candidate("host-a", 95, metric_type="disk", mount="/backup", sampled_at=NOW - timedelta(minutes=11)),
        candidate("host-b", 88, metric_type="disk", mount="/var"),
    ]

    normalized = normalize_metric_candidates(
        raw,
        host_meta={"host-a": {"interval": 300}, "host-b": {"interval": 300}},
        now=NOW,
    )
    rows = build_ranked_rows(normalized, host_meta={})

    assert [(row["instance_id"], row["usage_percent"], row["mount"]) for row in rows] == [
        ("host-a", 92.0, "/data"),
        ("host-b", 88.0, "/var"),
    ]


def test_disk_tie_uses_mount_path_and_fstype_ascending():
    raw = [
        candidate("host-a", 90, metric_type="disk", mount="/var"),
        candidate("host-a", 90, metric_type="disk", mount="/data"),
    ]

    normalized = normalize_metric_candidates(raw, host_meta={"host-a": {"interval": 300}}, now=NOW)

    assert normalized[0].labels["mount"] == "/data"

def test_ranked_rows_include_display_fallback_and_null_disk_fields_for_cpu():
    rows = build_ranked_rows(
        [candidate("instance-1", 12.345)],
        host_meta={"instance-1": {"host_name": "web-1", "ip": "10.0.0.1"}},
    )

    assert rows[0]["display_name"] == "web-1 (10.0.0.1)"
    assert rows[0]["usage_percent"] == 12.35
    assert rows[0]["mount"] is None
    assert rows[0]["path"] is None
    assert rows[0]["fstype"] is None


def test_service_queries_authorized_instances_and_returns_latest_cpu_rows():
    class FakeVictoriaMetrics:
        def __init__(self):
            self.queries = []

        def query(self, query, **kwargs):
            self.queries.append((query, kwargs))
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "host-1"}, "value": [NOW.timestamp(), "77.125"]},
                        {"metric": {"instance_id": "not-authorized"}, "value": [NOW.timestamp(), "99"]},
                    ]
                },
            }

    vm = FakeVictoriaMetrics()
    service = HostResourceTopService(vm_api=vm, now=NOW)
    rows = service.run(
        "cpu",
        [SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)],
    )

    assert rows[0]["instance_id"] == "host-1"
    assert rows[0]["usage_percent"] == 77.12
    assert "host_cpu_usage_percent" in vm.queries[0][0]
    assert "host_cpu_usage_percent_gauge" in vm.queries[0][0]
    assert vm.queries[0][1]["lookback_delta"] == "600s"

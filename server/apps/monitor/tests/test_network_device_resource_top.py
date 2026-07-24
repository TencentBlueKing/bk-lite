from datetime import datetime, timedelta, timezone

from apps.monitor.services.network_device_resource_top import (
    NetworkCandidate,
    NetworkDeviceResourceTopService,
    build_ranked_rows,
    normalize_candidates,
    validate_metric_type,
)


def test_network_candidates_are_filtered_to_fresh_supported_devices_and_ranked():
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    meta = {
        "sw-1": {"name": "Switch A", "ip": "10.0.0.1", "object_name": "Switch", "interval": 60},
        "router-1": {"name": "Router A", "ip": "10.0.0.2", "object_name": "Router", "interval": 60},
        "server-1": {"name": "Server", "ip": "10.0.0.3", "object_name": "Linux", "interval": 60},
    }
    candidates = [
        NetworkCandidate("sw-1", 80, now - timedelta(seconds=30), "cpu"),
        NetworkCandidate("router-1", 90, now - timedelta(seconds=30), "cpu"),
        NetworkCandidate("server-1", 99, now - timedelta(seconds=30), "cpu"),
        NetworkCandidate("sw-1", 70, now - timedelta(seconds=400), "cpu"),
    ]

    normalized = normalize_candidates(candidates, meta, now=now)
    rows = build_ranked_rows(normalized, meta)

    assert [row["instance_id"] for row in rows] == ["router-1", "sw-1"]
    assert rows[0]["value"] == 90.0
    assert rows[0]["rank"] == 1


def test_validate_metric_type_rejects_unknown_metric():
    assert validate_metric_type("traffic") == "traffic"
    try:
        validate_metric_type("disk")
    except ValueError as exc:
        assert "cpu" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_memory_fallback_is_supported_by_service():
    class FakeVM:
        def query(self, query, **kwargs):
            metric = query.split('"')[1]
            values = {
                "device_memory_used": "80",
                "device_memory_total": "100",
            }
            result = []
            if metric in values:
                result.append({
                    "metric": {"instance_id": "sw-1"},
                    "value": [datetime(2026, 7, 22, 12, tzinfo=timezone.utc).timestamp(), values[metric]],
                })
            return {"status": "success", "data": {"result": result}}

    instance = type("Instance", (), {
        "id": "sw-1", "name": "Switch A", "ip": None, "interval": 300,
        "monitor_object": type("Object", (), {"name": "Switch"})(),
    })()
    rows = __import__("apps.monitor.services.network_device_resource_top", fromlist=["NetworkDeviceResourceTopService"]).NetworkDeviceResourceTopService(
        vm_api=FakeVM(), now=datetime(2026, 7, 22, 12, tzinfo=timezone.utc)
    ).run("memory", [instance])
    assert rows[0]["value"] == 80.0


def test_service_matches_tuple_storage_id_with_raw_metric_instance_id():
    now = datetime(2026, 7, 22, 12, tzinfo=timezone.utc)

    class FakeVM:
        def query(self, query, **kwargs):
            metric = query.split('"')[1]
            value = "55" if metric == "device_cpu_usage" else "0"
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "switch-1"},
                            "value": [now.timestamp(), value],
                        }
                    ]
                },
            }

    instance = type(
        "Instance",
        (),
        {
            "id": "('switch-1',)",
            "name": "Switch A",
            "ip": "10.0.0.2",
            "interval": 300,
            "monitor_object": type("Object", (), {"name": "Switch"})(),
        },
    )()

    rows = NetworkDeviceResourceTopService(vm_api=FakeVM(), now=now).run(
        "cpu",
        [instance],
    )

    assert rows[0]["instance_id"] == "switch-1"
    assert rows[0]["value"] == 55.0

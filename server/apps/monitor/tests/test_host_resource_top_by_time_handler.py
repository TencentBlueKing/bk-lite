import time
from types import SimpleNamespace

from apps.monitor.nats import monitor as nm
from apps.monitor.services.host_resource_top import resolve_window_step, validate_window_aggregation


def _series(instance_id: str, values: list[float]) -> dict:
    now = time.time()
    return {
        "metric": {"instance_id": instance_id},
        "values": [[now - 60 * (len(values) - index), str(value)] for index, value in enumerate(values)],
    }


def _patch_scope(monkeypatch, instances: dict) -> None:
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids: (instances, None),
    )


def _install_vm(monkeypatch, result: list[dict]) -> None:
    class FakeVM:
        def __init__(self):
            self.calls: list[tuple] = []

        def query_range(self, query, start, end, step):
            self.calls.append((query, start, end, step))
            return {"status": "success", "data": {"result": result}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)


def test_top_by_time_ranks_hosts_by_window_peak(monkeypatch):
    _patch_scope(
        monkeypatch,
        {
            "host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300),
            "host-2": SimpleNamespace(id="host-2", name="web-2", ip="10.0.0.2", interval=300),
        },
    )
    _install_vm(
        monkeypatch,
        [
            _series("host-1", [30, 40, 55]),
            _series("host-2", [20, 25, 28]),
        ],
    )

    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert [row["instance_id"] for row in out["data"]] == ["host-1", "host-2"]
    assert out["data"][0]["usage_percent"] == 55
    assert out["data"][0]["peak_percent"] == 55
    assert out["data"][0]["avg_percent"] == 41.67
    assert out["data"][0]["rank"] == 1


def test_top_by_time_avg_aggregation_reranks(monkeypatch):
    """瞬时打满但均值不高的机器，avg 排序时应排在稳定高占用之后。"""
    _patch_scope(
        monkeypatch,
        {
            "host-spike": SimpleNamespace(id="host-spike", name="spike", ip="10.0.0.1", interval=300),
            "host-steady": SimpleNamespace(id="host-steady", name="steady", ip="10.0.0.2", interval=300),
        },
    )
    _install_vm(
        monkeypatch,
        [
            _series("host-spike", [1, 1, 99]),
            _series("host-steady", [60, 62, 64]),
        ],
    )

    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        aggregation="avg",
        user_info={"user": "u", "team": 1},
    )

    assert [row["instance_id"] for row in out["data"]] == ["host-steady", "host-spike"]
    assert out["data"][0]["usage_percent"] == 62


def test_top_by_time_folds_disk_mounts_to_worst(monkeypatch):
    _patch_scope(monkeypatch, {"host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)})

    class FakeVM:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-1", "mount": "/"},
                            "values": [[time.time(), "20"]],
                        },
                        {
                            "metric": {"instance_id": "host-1", "mount": "/data"},
                            "values": [[time.time(), "91"]],
                        },
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)

    out = nm.get_host_resource_top_by_time("disk", lookback_minutes=5, user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert out["data"][0]["usage_percent"] == 91


def test_top_by_time_accepts_absolute_time_range(monkeypatch):
    _patch_scope(monkeypatch, {"host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)})
    _install_vm(monkeypatch, [_series("host-1", [42])])

    out = nm.get_host_resource_top_by_time(
        "cpu",
        time=["2026-09-28T09:00:00Z", "2026-09-28T09:05:00Z"],
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert out["data"][0]["usage_percent"] == 42


def test_top_by_time_requires_a_window(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("missing window must fail before querying")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)

    out = nm.get_host_resource_top_by_time("cpu", user_info={"user": "u", "team": 1})

    assert out["result"] is False
    assert "lookback_minutes" in out["message"]


def test_top_by_time_rejects_unsupported_metric_type(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("invalid metric type must fail before querying")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)

    out = nm.get_host_resource_top_by_time("network", lookback_minutes=5, user_info={"user": "u", "team": 1})

    assert out["result"] is False


def test_top_by_time_rejects_invalid_aggregation(monkeypatch):
    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        aggregation="median",
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is False
    assert "aggregation" in out["message"]


def test_top_by_time_caps_limit(monkeypatch):
    _patch_scope(monkeypatch, {"host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)})
    _install_vm(monkeypatch, [_series("host-1", [42])])

    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        limit=100000,
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True


def test_top_by_time_narrows_to_authorized_hosts_only(monkeypatch):
    _patch_scope(
        monkeypatch,
        {
            "host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300),
            "host-2": SimpleNamespace(id="host-2", name="web-2", ip="10.0.0.2", interval=300),
        },
    )
    _install_vm(
        monkeypatch,
        [
            _series("host-1", [58]),
            _series("host-2", [10]),
        ],
    )

    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        instance_ids=["host-1", "host-unauthorized"],
        user_info={"user": "u", "team": 1},
    )

    assert [row["instance_id"] for row in out["data"]] == ["host-1"]


def test_top_by_time_empty_instance_ids_does_not_fallback(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    _patch_scope(monkeypatch, {"host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)

    out = nm.get_host_resource_top_by_time(
        "cpu",
        lookback_minutes=5,
        instance_ids=[],
        user_info={"user": "u", "team": 1},
    )

    assert out == {"result": True, "data": [], "message": ""}


def test_validate_window_aggregation_defaults_to_max():
    assert validate_window_aggregation("") == "max"
    assert validate_window_aggregation(None) == "max"
    assert validate_window_aggregation("AVG") == "avg"


def test_window_step_keeps_short_windows_dense():
    """5 分钟窗口若用 5m step 可能整窗取不到点，必须落到更细的 step。"""
    assert resolve_window_step(300) == "1m"
    assert resolve_window_step(600) == "1m"
    assert resolve_window_step(1800) == "5m"
    assert resolve_window_step(7200) == "15m"

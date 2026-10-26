import logging
from types import SimpleNamespace

import pytest

from apps.core.logger import SafeLogException
from apps.monitor.nats import monitor as nm


def _patch_scope(monkeypatch, instances):
    monkeypatch.setattr(
        nm,
        "_get_nats_actor_scope",
        lambda user_info: (None, 1, False, frozenset({1}), False, None),
    )
    monkeypatch.setattr(
        nm,
        "_get_authorized_monitor_instances",
        lambda user_info, scope_ids, monitor_obj_id=None: (instances, None),
    )


def test_host_instance_list_returns_authorized_hosts_only(monkeypatch):
    class FakeManager:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=7)

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    captured = {}

    def fake_auth(user_info, scope_ids, monitor_obj_id=None):
        captured["monitor_obj_id"] = monitor_obj_id
        return {
            "host-1": SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1"),
            "switch-1": SimpleNamespace(id="switch-1", name="sw", ip="10.0.0.9"),
        }, None

    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", fake_auth)

    out = nm.get_host_instance_list(user_info={"user": "u", "team": 1})

    assert captured["monitor_obj_id"] == 7
    assert out["result"] is True
    assert out["data"] == [
        {"instance_id": "switch-1", "display_name": "sw (10.0.0.9)"},
        {"instance_id": "host-1", "display_name": "web-1 (10.0.0.1)"},
    ]


def test_host_metric_range_empty_selection_does_not_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_metric_range(
        metric_type="cpu",
        instance_ids=[],
        time=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        user_info={"user": "u", "team": 1},
    )
    assert out == {"result": True, "data": {}, "message": ""}


def test_host_metric_range_drops_unauthorized_and_folds(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})

    class FakeVM:
        def query_range(self, query, start, end, step):
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "host-1", "path": "/"}, "values": [[1, "40"]]},
                        {"metric": {"instance_id": "host-1", "path": "/data"}, "values": [[1, "90"]]},
                        {"metric": {"instance_id": "host-2"}, "values": [[1, "1"]]},
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    out = nm.get_host_metric_range(
        metric_type="disk",
        instance_ids=["host-1", "host-2"],
        time=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        user_info={"user": "u", "team": 1},
    )
    assert out["result"] is True
    assert out["data"] == {"web-1 (10.0.0.1)": [[1.0, 90.0]]}


def test_host_resource_snapshot_empty_selection_skips_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_snapshot(instance_ids=[], user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"]["host_count"] == 0
    assert "healthy" not in out["data"]


def test_host_resource_snapshot_unknown_scope_still_skips_empty_selection(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("unknown scope must keep the empty snapshot")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_snapshot(scope="fleet", instance_ids=[], user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"]["host_count"] == 0


def test_host_resource_snapshot_empty_selection_with_time_skips_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty selection must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    time_range = ["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"]
    for scope in (None, "", "selected", "fleet"):
        kwargs = {
            "instance_ids": [],
            "time": time_range,
            "user_info": {"user": "u", "team": 1},
        }
        if scope is not None:
            kwargs["scope"] = scope
        out = nm.get_host_resource_snapshot(**kwargs)
        assert out["result"] is True
        assert out["data"]["host_count"] == 0


def test_host_resource_snapshot_all_authorized_without_time_uses_near_realtime(monkeypatch):
    host = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=60)
    captured = {}

    class FakeManager:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=7)

    def fake_auth(user_info, scope_ids, monitor_obj_id=None):
        captured["monitor_obj_id"] = monitor_obj_id
        return {"host-1": host}, None

    def fake_run(instances):
        captured["ids"] = [item.id for item in instances]
        return {
            "host_count": 1,
            "avg_cpu": 11.0,
            "avg_memory": 22.0,
            "avg_disk": 33.0,
            "max_cpu": 44.0,
            "max_cpu_host": "web-1 (10.0.0.1)",
            "max_memory": 55.0,
            "max_memory_host": "web-1 (10.0.0.1)",
        }

    def fail_window(**kwargs):
        raise AssertionError("near realtime must not use the window builder")

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", fake_auth)
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: object())
    monkeypatch.setattr(nm, "build_windowed_host_averages", fail_window)
    monkeypatch.setattr(nm, "HostResourceSnapshotService", lambda **kwargs: SimpleNamespace(run=fake_run))

    for scope, time_value in (("all_authorized", None), ("All_Authorized", ""), ("all_authorized", [])):
        captured.pop("ids", None)
        kwargs = {
            "scope": scope,
            "instance_ids": ["ignored"],
            "user_info": {"user": "u", "team": 1},
        }
        if time_value is not None:
            kwargs["time"] = time_value
        out = nm.get_host_resource_snapshot(**kwargs)
        assert out["result"] is True
        assert out["data"]["avg_cpu"] == 11.0
        assert out["data"]["max_cpu"] == 44.0
        assert captured["ids"] == ["host-1"]
        assert captured["monitor_obj_id"] == 7


def test_host_resource_snapshot_all_authorized_without_hosts_skips_query(monkeypatch):
    class FailVM:
        def __init__(self):
            raise AssertionError("empty fleet must not query")

    class MissingHost:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return None

    class EmptyFleet:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=7)

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    monkeypatch.setattr(nm, "_get_nats_actor_scope", lambda user_info: (None, 1, False, frozenset({1}), False, None))
    monkeypatch.setattr(nm, "_get_authorized_monitor_instances", lambda *args, **kwargs: ({}, None))

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=MissingHost()))
    missing = nm.get_host_resource_snapshot(scope="all_authorized", time=10080, user_info={"user": "u", "team": 1})
    assert missing["result"] is True
    assert missing["data"]["host_count"] == 0

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=EmptyFleet()))
    for time_value in (None, ["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"]):
        kwargs = {"scope": "all_authorized", "instance_ids": ["ignored"], "user_info": {"user": "u", "team": 1}}
        if time_value is not None:
            kwargs["time"] = time_value
        out = nm.get_host_resource_snapshot(**kwargs)
        assert out["result"] is True
        assert out["data"]["host_count"] == 0


def test_host_resource_snapshot_selected_with_time_uses_window(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})
    captured = {}

    def fake_build(*, vm_api, instances, time_range, step="5m"):
        del vm_api, step
        captured["ids"] = [item.id for item in instances]
        captured["time"] = time_range
        return {
            "host_count": 1,
            "avg_cpu": 9.0,
            "avg_memory": None,
            "avg_disk": None,
            "max_cpu": None,
            "max_cpu_host": None,
            "max_memory": None,
            "max_memory_host": None,
        }

    def fail_service(**kwargs):
        raise AssertionError("selected window must not use the near-realtime service")

    class FailHostLookup:
        def filter(self, **kwargs):
            raise AssertionError("selected scope must not load the host fleet")

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FailHostLookup()))
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: object())
    monkeypatch.setattr(nm, "build_windowed_host_averages", fake_build)
    monkeypatch.setattr(nm, "HostResourceSnapshotService", fail_service)

    for scope in (None, "selected", "fleet"):
        captured.clear()
        kwargs = {
            "instance_ids": ["host-1"],
            "time": ["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"],
            "user_info": {"user": "u", "team": 1},
        }
        if scope is not None:
            kwargs["scope"] = scope
        out = nm.get_host_resource_snapshot(**kwargs)
        assert out["result"] is True
        assert out["data"]["avg_cpu"] == 9.0
        assert out["data"]["max_cpu"] is None
        assert captured["ids"] == ["host-1"]
        assert captured["time"][0].startswith("2026-08-01")


def test_host_resource_snapshot_all_authorized_uses_windowed_hosts(monkeypatch):
    host = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", cmdb_id="cmdb-1")

    class FakeManager:
        def filter(self, **kwargs):
            assert kwargs == {"name": "Host"}
            return self

        def first(self):
            return SimpleNamespace(id=7)

    captured = {}

    def fake_build(*, vm_api, instances, time_range, step="5m"):
        del vm_api, step
        captured["ids"] = [item.id for item in instances]
        captured["time"] = time_range
        return {
            "host_count": 1,
            "avg_cpu": 12.5,
            "avg_memory": 30.0,
            "avg_disk": 40.0,
            "max_cpu": None,
            "max_cpu_host": None,
            "max_memory": None,
            "max_memory_host": None,
        }

    monkeypatch.setattr(nm, "MonitorObject", SimpleNamespace(objects=FakeManager()))
    _patch_scope(monkeypatch, {"host-1": host})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: object())
    monkeypatch.setattr(nm, "build_windowed_host_averages", fake_build)

    out = nm.get_host_resource_snapshot(
        scope="all_authorized",
        instance_ids=["ignored"],
        time=["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"],
        user_info={"user": "u", "team": 1},
    )

    assert out["result"] is True
    assert out["data"]["avg_cpu"] == 12.5
    assert out["data"]["max_cpu"] is None
    assert captured["ids"] == ["host-1"]
    assert captured["time"][0].startswith("2026-08-01")


def test_host_resource_snapshot_returns_avg_max_without_health(monkeypatch):
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})
    monkeypatch.setattr(
        nm,
        "HostResourceSnapshotService",
        lambda **kwargs: SimpleNamespace(
            run=lambda instances: {
                "host_count": 1,
                "avg_cpu": 40.0,
                "avg_memory": 20.0,
                "avg_disk": 70.0,
                "max_cpu": 40.0,
                "max_cpu_host": "web-1 (10.0.0.1)",
                "max_memory": 20.0,
                "max_memory_host": "web-1 (10.0.0.1)",
            }
        ),
    )
    out = nm.get_host_resource_snapshot(instance_ids=["host-1"], user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"]["host_count"] == 1
    assert "healthy" not in out["data"]
    assert "unhealthy" not in out["data"]


def test_host_resource_snapshot_accepts_logical_instance_id(monkeypatch):
    allowed = SimpleNamespace(id="('MTVmOTFiYTM5ODZk',)", name="local", ip="10.10.41.149", interval=60)
    _patch_scope(monkeypatch, {allowed.id: allowed})
    captured = {}
    monkeypatch.setattr(
        nm,
        "HostResourceSnapshotService",
        lambda **kwargs: SimpleNamespace(run=lambda instances: captured.update(instances=instances) or {"host_count": len(instances)}),
    )

    out = nm.get_host_resource_snapshot(instance_ids=["MTVmOTFiYTM5ODZk"], user_info={"user": "u", "team": 1})

    assert out["result"] is True
    assert captured["instances"] == [allowed]
    assert out["data"]["host_count"] == 1


def test_host_resource_snapshot_rejects_cmdb_locators(monkeypatch):
    from apps.monitor.services.host_dashboard import CMDB_LOCATOR_USED_AS_MONITOR_INSTANCE_MESSAGE

    allowed = SimpleNamespace(id="('MTVmOTFiYTM5ODZk',)", name="local", ip="10.10.41.149", interval=60)
    _patch_scope(monkeypatch, {allowed.id: allowed})

    class FailVM:
        def __init__(self):
            raise AssertionError("cmdb locators must not query")

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FailVM)
    out = nm.get_host_resource_snapshot(
        instance_ids=["100000000001"],
        user_info={"user": "u", "team": 1},
    )
    assert out["result"] is False
    assert out["message"] == CMDB_LOCATOR_USED_AS_MONITOR_INSTANCE_MESSAGE


@pytest.mark.parametrize(
    ("stage", "with_time"),
    [("window_query", True), ("near_realtime_query", False)],
)
def test_host_snapshot_failure_logs_failed_stage_without_payload(monkeypatch, caplog, stage, with_time):
    sentinel = "password=snapshot-secret-token"
    original_error = RuntimeError(sentinel)
    allowed = SimpleNamespace(id="host-1", name="web-1", ip="10.0.0.1", interval=300)
    _patch_scope(monkeypatch, {"host-1": allowed})

    class DummyVM:
        def __init__(self, *args, **kwargs):
            return None

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", DummyVM)
    if with_time:

        def boom(**kwargs):
            raise original_error

        monkeypatch.setattr(nm, "build_windowed_host_averages", boom)
    else:

        class BoomService:
            def __init__(self, vm_api=None):
                return None

            def run(self, instances):
                raise original_error

        monkeypatch.setattr(nm, "HostResourceSnapshotService", BoomService)

    kwargs = {"instance_ids": ["host-1"], "user_info": {"user": "u", "team": 1, "password": sentinel}}
    if with_time:
        kwargs["time"] = ["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"]

    with caplog.at_level(logging.ERROR, logger="nats"):
        out = nm.get_host_resource_snapshot(**kwargs)

    assert out["result"] is False
    assert out["message"] == "主机资源快照查询失败"
    assert out["data"] == nm.empty_host_snapshot()
    records = [record for record in caplog.records if record.name == "nats" and "host_resource_snapshot_failed" in record.msg]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert "failed_stage=%s" in record.msg
    assert "error_type=%s" in record.msg
    assert record.args == (stage, "RuntimeError")
    assert f"failed_stage={stage}" in record.getMessage()
    assert "error_type=RuntimeError" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is original_error.__traceback__
    assert record.exc_info[1] is not original_error
    assert original_error.args == (sentinel,)
    assert sentinel not in record.msg
    assert sentinel not in str(record.args)
    assert sentinel not in record.getMessage()
    assert sentinel not in caplog.text

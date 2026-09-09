"""get_zombie_host_report NATS handler：空选择、上限、授权过滤、拼表与分页。"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.core.logger import SafeLogException
from apps.monitor.nats import monitor as nm
from apps.monitor.services.zombie_host_report import DEFAULT_THRESHOLDS, UNBOUNDED

pytestmark = pytest.mark.unit

REQUIRED_METRIC_KEYS = (
    "cpu_avg",
    "cpu_max",
    "mem_avg",
    "mem_max",
    "packets_recv_avg",
    "packets_recv_max",
    "io_max",
    "login_count",
    "login_status",
)

HOST_U1 = {
    "inst_uuid": "u1",
    "monitor_id": "m1",
    "host_name": "h1",
    "ip": "10.0.0.1",
    "os_type": "1",
    "os_type_label": "Linux",
    "node_id": "n1",
    "biz_name": "交易",
    "zombie_whitelist": "no",
}
HOST_U2 = {
    "inst_uuid": "u2",
    "monitor_id": "m2",
    "host_name": "h2",
    "ip": "10.0.0.2",
    "os_type": "1",
    "os_type_label": "Linux",
    "node_id": "n2",
    "biz_name": "交易",
    "zombie_whitelist": "no",
}


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


def _unbounded_thresholds():
    return {key: UNBOUNDED for key in DEFAULT_THRESHOLDS}


def _fail_vm():
    return (_ for _ in ()).throw(AssertionError("no vm"))


def _empty_vm(queried=None):
    class FakeVM:
        def query(self, q, *a, **k):
            if queried is not None:
                queried.append(q)
            return {"status": "success", "data": {"result": []}}

    return FakeVM


def test_empty_inst_uuids_does_not_query(monkeypatch):
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", lambda: (_ for _ in ()).throw(AssertionError("no vm")))
    login_called = []
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda *a, **k: login_called.append(1) or {"result": True, "data": []},
    )
    loaded = []
    monkeypatch.setattr(
        nm,
        "load_selected_hosts",
        lambda *a, **k: loaded.append(1) or [],
    )
    out = nm.get_zombie_host_report(inst_uuids=[], time=10080, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": {"items": [], "count": 0, "page": 1, "page_size": 20}, "message": ""}
    assert login_called == []
    assert loaded == []


def test_none_inst_uuids_is_empty_success_without_query(monkeypatch):
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    login_called = []
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: login_called.append(1))
    out = nm.get_zombie_host_report(inst_uuids=None, user_info={"user": "u", "team": 1})
    assert out["result"] is True
    assert out["data"] == {"items": [], "count": 0, "page": 1, "page_size": 20}
    assert login_called == []


def test_over_100_hosts_fails_without_truncate(monkeypatch):
    loaded = []
    monkeypatch.setattr(nm, "load_selected_hosts", lambda *a, **k: loaded.append(1) or [])
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    login_called = []
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: login_called.append(1))
    out = nm.get_zombie_host_report(inst_uuids=[f"u{i}" for i in range(101)], user_info={})
    assert out["result"] is False
    assert "100" in out["message"]
    assert out["data"]["items"] == []
    assert out["data"]["count"] == 0
    assert loaded == []
    assert login_called == []


def test_empty_system_uuids_does_not_query(monkeypatch):
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    login_called = []
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda *a, **k: login_called.append(1) or {"result": True, "data": []},
    )
    loaded = []
    monkeypatch.setattr(nm, "load_selected_hosts", lambda *a, **k: loaded.append(1) or [])
    expanded = []
    monkeypatch.setattr(nm, "load_hosts_for_systems", lambda *a, **k: expanded.append(1) or [dict(HOST_U1)])
    out = nm.get_zombie_host_report(system_uuids=[], inst_uuids=["u1"], time=10080, user_info={"user": "u", "team": 1})
    assert out == {"result": True, "data": {"items": [], "count": 0, "page": 1, "page_size": 20}, "message": ""}
    assert login_called == []
    assert loaded == []
    assert expanded == []


def test_system_uuids_expand_then_load_hosts(monkeypatch):
    _patch_scope(monkeypatch, {"m1": {"id": "m1"}})
    captured = {}
    loaded = []

    def fake_hosts(system_uuids, user_info):
        captured["systems"] = list(system_uuids)
        captured["user"] = user_info
        return [dict(HOST_U1)]

    monkeypatch.setattr(nm, "load_hosts_for_systems", fake_hosts)
    monkeypatch.setattr(nm, "load_selected_hosts", lambda *a, **k: loaded.append(1) or [])
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, time_range, user_info=None: {"result": True, "data": []},
    )
    out = nm.get_zombie_host_report(
        system_uuids=["s1", "s1"],
        inst_uuids=["ignored"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert captured["systems"] == ["s1"]
    assert loaded == []
    assert out["data"]["count"] == 1
    assert out["data"]["items"][0]["inst_uuid"] == "u1"


def test_system_expand_over_100_hosts_fails_without_truncate(monkeypatch):
    _patch_scope(monkeypatch, {"m1": {"id": "m1"}})

    def fake_hosts(*a, **k):
        raise ValueError("一次最多查询 100 台主机")

    monkeypatch.setattr(nm, "load_hosts_for_systems", fake_hosts)
    loaded = []
    monkeypatch.setattr(nm, "load_selected_hosts", lambda *a, **k: loaded.append(1) or [])
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    out = nm.get_zombie_host_report(system_uuids=["s1"], user_info={"user": "u", "team": 1})
    assert out["result"] is False
    assert "100" in out["message"]
    assert loaded == []


def test_drops_unauthorized_monitor_id(monkeypatch):
    identities = [
        {
            "inst_uuid": "u1",
            "monitor_id": "m1",
            "host_name": "h1",
            "ip": "10.0.0.1",
            "os_type": "1",
            "node_id": "n1",
        },
        {
            "inst_uuid": "u2",
            "monitor_id": "m2",
            "host_name": "h2",
            "ip": "10.0.0.2",
            "os_type": "1",
            "node_id": "n2",
        },
    ]
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: identities)
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    queried = []

    class FakeVM:
        def query(self, q, *a, **k):
            queried.append(q)
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    login_hosts = []

    def fake_logins(hosts, *a, **k):
        login_hosts.extend(hosts)
        return {"result": True, "data": []}

    monkeypatch.setattr(nm, "count_successful_logins", fake_logins)
    out = nm.get_zombie_host_report(
        inst_uuids=["u1", "u2"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert [h["monitor_id"] for h in login_hosts] == ["m1"]
    assert all("m2" not in q for q in queried)
    assert all("instance_id=~" in q and "m1" in q for q in queried)
    assert [row["monitor_id"] for row in out["data"]["items"]] == ["m1"]


def test_after_auth_filter_empty_is_success_without_vm_or_login(monkeypatch):
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U2)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    login_called = []
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: login_called.append(1))
    out = nm.get_zombie_host_report(
        inst_uuids=["u2"],
        time=10080,
        user_info={"user": "u", "team": 1},
    )
    assert out == {"result": True, "data": {"items": [], "count": 0, "page": 1, "page_size": 20}, "message": ""}
    assert login_called == []


def test_os_type_and_whitelist_filters_identities(monkeypatch):
    identities = [
        {**HOST_U1, "os_type": "1", "zombie_whitelist": "no"},
        {**HOST_U2, "os_type": "2", "os_type_label": "Windows", "zombie_whitelist": "yes", "monitor_id": "m2"},
        {
            "inst_uuid": "u3",
            "monitor_id": "m3",
            "host_name": "h3",
            "ip": "10.0.0.3",
            "os_type": "1",
            "os_type_label": "Linux",
            "zombie_whitelist": "yes",
            "node_id": "n3",
        },
    ]
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: identities)
    _patch_scope(
        monkeypatch,
        {
            "m1": SimpleNamespace(id="m1"),
            "m2": SimpleNamespace(id="m2"),
            "m3": SimpleNamespace(id="m3"),
        },
    )
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    login_hosts = []
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, *a, **k: login_hosts.extend(hosts) or {"result": True, "data": []},
    )
    out = nm.get_zombie_host_report(
        inst_uuids=["u1", "u2", "u3"],
        os_type="1",
        zombie_whitelist="no",
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert [h["monitor_id"] for h in login_hosts] == ["m1"]
    assert [row["inst_uuid"] for row in out["data"]["items"]] == ["u1"]


def test_cmdb_false_result_fails_without_half_table(monkeypatch):
    monkeypatch.setattr(
        nm,
        "load_selected_hosts",
        lambda inst_uuids, user_info: {"result": False, "data": [dict(HOST_U1)], "message": "cmdb failed"},
    )
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _fail_vm)
    login_called = []
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: login_called.append(1))
    out = nm.get_zombie_host_report(inst_uuids=["u1"], user_info={"user": "u", "team": 1})
    assert out["result"] is False
    assert out["data"]["items"] == []
    assert login_called == []


def test_login_false_result_fails_without_half_table(monkeypatch):
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, time_range, user_info=None: {
            "result": False,
            "data": [{"monitor_id": "m1", "login_count": 3, "login_status": "counted"}],
            "message": "log failed",
        },
    )
    out = nm.get_zombie_host_report(
        inst_uuids=["u1"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is False
    assert out["data"]["items"] == []
    assert out["data"]["count"] == 0


def test_login_failure_logs_failed_stage_login_count(monkeypatch, caplog):
    sentinel = "password=login-secret-token"
    original_error = RuntimeError(sentinel)

    def boom(hosts, time_range, user_info=None):
        raise original_error

    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    monkeypatch.setattr(nm, "count_successful_logins", boom)

    with caplog.at_level(logging.ERROR, logger="monitor"):
        out = nm.get_zombie_host_report(
            inst_uuids=["u1"],
            time=10080,
            user_info={"user": "u", "team": 1},
            **_unbounded_thresholds(),
        )

    assert out["result"] is False
    assert out["data"]["items"] == []
    records = [record for record in caplog.records if "login_count" in str(record.msg) or "login_count" in record.getMessage()]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert "failed_stage=%s" in record.msg
    assert "error_type=%s" in record.msg
    assert "login_count" in record.args
    assert "RuntimeError" in record.args
    assert "failed_stage=login_count" in record.getMessage()
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


def test_pagination_applies_after_thresholds(monkeypatch):
    hosts = [
        {**HOST_U1, "inst_uuid": "u1", "monitor_id": "m1", "host_name": "keep-a"},
        {**HOST_U2, "inst_uuid": "u2", "monitor_id": "m2", "host_name": "drop-cpu"},
        {
            **HOST_U1,
            "inst_uuid": "u3",
            "monitor_id": "m3",
            "host_name": "keep-b",
            "ip": "10.0.0.3",
        },
    ]
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: hosts)
    _patch_scope(
        monkeypatch,
        {
            "m1": SimpleNamespace(id="m1"),
            "m2": SimpleNamespace(id="m2"),
            "m3": SimpleNamespace(id="m3"),
        },
    )

    class FakeVM:
        def query(self, q, *a, **k):
            if "avg_over_time" in q and "cpu_usage_idle" in q:
                return {
                    "status": "success",
                    "data": {
                        "result": [
                            {"metric": {"instance_id": "m1"}, "value": [1, "5"]},
                            {"metric": {"instance_id": "m2"}, "value": [1, "50"]},
                            {"metric": {"instance_id": "m3"}, "value": [1, "8"]},
                        ]
                    },
                }
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, *a, **k: {
            "result": True,
            "data": [{"monitor_id": h["monitor_id"], "login_count": 1, "login_status": "counted"} for h in hosts],
        },
    )
    thresholds = _unbounded_thresholds()
    thresholds["cpu_avg_max"] = 19
    out = nm.get_zombie_host_report(
        inst_uuids=["u1", "u2", "u3"],
        time=10080,
        user_info={"user": "u", "team": 1},
        page=2,
        page_size=1,
        **thresholds,
    )
    assert out["result"] is True
    assert out["data"]["count"] == 2
    assert out["data"]["page"] == 2
    assert out["data"]["page_size"] == 1
    assert [row["host_name"] for row in out["data"]["items"]] == ["keep-b"]


def test_each_row_has_all_metric_keys_even_if_none(monkeypatch):
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: {"result": True, "data": []})
    out = nm.get_zombie_host_report(
        inst_uuids=["u1"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert out["data"]["count"] == 1
    row = out["data"]["items"][0]
    for key in REQUIRED_METRIC_KEYS:
        assert key in row
    assert row["cpu_avg"] is None
    assert row["login_count"] is None
    assert row["login_status"] == "uncollected"


def test_completed_log_records_counts_and_elapsed(monkeypatch, caplog):
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    monkeypatch.setattr(nm, "VictoriaMetricsAPI", _empty_vm())
    monkeypatch.setattr(nm, "count_successful_logins", lambda *a, **k: {"result": True, "data": []})
    with caplog.at_level(logging.INFO, logger="monitor"):
        out = nm.get_zombie_host_report(
            inst_uuids=["u1"],
            time=10080,
            user_info={"user": "u", "team": 1},
            **_unbounded_thresholds(),
        )
    assert out["result"] is True
    assert out["data"]["count"] == 1
    records = [
        record
        for record in caplog.records
        if "zombie_host_report_completed" in str(record.msg) or "zombie_host_report_completed" in record.getMessage()
    ]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.INFO
    assert record.msg == ("event=zombie_host_report_completed identity_count=%s authorized_count=%s result_count=%s elapsed_ms=%s")
    assert record.args[0] == 1
    assert record.args[1] == 1
    assert record.args[2] == 1
    assert isinstance(record.args[3], int)
    assert record.args[3] >= 0
    assert "event=zombie_host_report_completed" in record.getMessage()
    assert "identity_count=1" in record.getMessage()
    assert "authorized_count=1" in record.getMessage()
    assert "result_count=1" in record.getMessage()
    assert "elapsed_ms=" in record.getMessage()


def test_vm_queries_authorized_ids_only_and_drops_extra_instance_ids(monkeypatch):
    identities = [dict(HOST_U1), dict(HOST_U2)]
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: identities)
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    queried = []

    class FakeVM:
        def query(self, q, *a, **k):
            queried.append(q)
            return {
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"instance_id": "m1"}, "value": [1, "4"]},
                        {"metric": {"instance_id": "m2"}, "value": [1, "99"]},
                        {"metric": {"instance_id": "m-extra"}, "value": [1, "7"]},
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, *a, **k: {
            "result": True,
            "data": [{"monitor_id": "m1", "login_count": 0, "login_status": "counted"}],
        },
    )
    out = nm.get_zombie_host_report(
        inst_uuids=["u1", "u2"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert queried
    for query in queried:
        assert "m1" in query
        assert "m2" not in query
        assert "m-extra" not in query
        assert "instance_id=~" in query
    row = out["data"]["items"][0]
    assert row["monitor_id"] == "m1"
    assert row["cpu_avg"] == 4.0
    assert row["cpu_max"] == 4.0


def test_default_time_is_10080_minutes(monkeypatch):
    fixed = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(nm, "datetime", FrozenDateTime)
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})
    queried = []
    login_ranges = []

    class FakeVM:
        def query(self, q, *a, **k):
            queried.append(q)
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)

    def fake_logins(hosts, time_range, user_info=None):
        login_ranges.append(time_range)
        return {"result": True, "data": []}

    monkeypatch.setattr(nm, "count_successful_logins", fake_logins)
    out = nm.get_zombie_host_report(
        inst_uuids=["u1"],
        time=None,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert login_ranges
    start, end = login_ranges[0]
    assert start.endswith("Z")
    assert end.endswith("Z")
    assert "604800s" in queried[0]
    assert all("604800s" in q for q in queried)


def test_packets_fold_sums_nics_io_takes_max_disk(monkeypatch):
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [dict(HOST_U1)])
    _patch_scope(monkeypatch, {"m1": SimpleNamespace(id="m1")})

    class FakeVM:
        def query(self, q, *a, **k):
            if "net_packets_recv" in q:
                return {
                    "status": "success",
                    "data": {
                        "result": [
                            {"metric": {"instance_id": "m1", "device": "eth0"}, "value": [1, "10"]},
                            {"metric": {"instance_id": "m1", "device": "eth1"}, "value": [1, "5"]},
                        ]
                    },
                }
            if "diskio_io_util" in q:
                return {
                    "status": "success",
                    "data": {
                        "result": [
                            {"metric": {"instance_id": "m1", "device": "sda"}, "value": [1, "10"]},
                            {"metric": {"instance_id": "m1", "device": "sdb"}, "value": [1, "40"]},
                        ]
                    },
                }
            return {"status": "success", "data": {"result": []}}

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda *a, **k: {"result": True, "data": [{"monitor_id": "m1", "login_count": 2, "login_status": "counted"}]},
    )
    out = nm.get_zombie_host_report(
        inst_uuids=["u1"],
        time=["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"],
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    row = out["data"]["items"][0]
    assert row["packets_recv_avg"] == 15.0
    assert row["packets_recv_max"] == 15.0
    assert row["io_max"] == 40.0
    assert row["login_count"] == 2
    assert row["login_status"] == "counted"


class _GroupQuery:
    def __init__(self, rows):
        self._rows = rows

    def values(self, *fields):
        return self._rows


def _stub_groups(monkeypatch, rows=None):
    from apps.system_mgmt.models import Group

    rows = rows if rows is not None else [{"id": 1, "name": "交易"}]
    monkeypatch.setattr(Group.objects, "filter", lambda **kw: _GroupQuery(rows))


def _host_entity(inst_uuid, monitor_id, host_name=None, ip=None):
    suffix = inst_uuid[-1]
    return {
        "inst_uuid": inst_uuid,
        "inst_name": host_name or f"web-{suffix}",
        "ip_addr": ip or f"10.0.0.{suffix}",
        "os_type": "1",
        "monitor_id": monitor_id,
        "organization": [1],
        "node_id": f"n{suffix}",
        "zombie_whitelist": "no",
    }


def test_load_selected_hosts_uses_cmdb_batch_and_drops_empty_monitor_id(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    captured = {}
    batch = {
        "u1": _host_entity("u1", "m1"),
        "u2": _host_entity("u2", ""),
        "u9": _host_entity("u9", "m9", host_name="other", ip="10.0.0.9"),
    }

    class FakeCMDB:
        def __init__(self, *args, **kwargs):
            pass

        def search_instances_batch(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"result": True, "data": batch}

        def get_monitor_ids_by_inst_uuids(self, **kwargs):
            captured["auth"] = kwargs
            return {
                "result": True,
                "data": {"items": [{"inst_uuid": uuid, "monitor_id": entity.get("monitor_id") or ""} for uuid, entity in batch.items()]},
                "message": "",
            }

    monkeypatch.setattr(zq, "CMDB", FakeCMDB)
    _stub_groups(monkeypatch)
    user_info = {"user": "u", "team": 1}
    rows = zq.load_selected_hosts(["u1", "u2"], user_info)
    assert captured["kwargs"]["model_id"] == "host"
    assert captured["kwargs"]["protocol_version"] == 2
    assert captured["kwargs"]["inst_uuids"] == ["u1", "u2"]
    assert captured["kwargs"]["organization_ids"] == [1]
    assert captured["auth"]["inst_uuids"] == ["u1", "u2"]
    assert captured["auth"]["user_info"] == user_info
    assert [row["inst_uuid"] for row in rows] == ["u1"]
    assert rows[0]["monitor_id"] == "m1"
    assert rows[0]["host_name"] == "web-1"


def test_load_selected_hosts_resolves_biz_name_from_group(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    class FakeCMDB:
        def __init__(self, *args, **kwargs):
            pass

        def search_instances_batch(self, **kwargs):
            return {
                "result": True,
                "data": {"u1": _host_entity("u1", "m1")},
            }

        def get_monitor_ids_by_inst_uuids(self, **kwargs):
            return {
                "result": True,
                "data": {"items": [{"inst_uuid": "u1", "monitor_id": "m1"}]},
                "message": "",
            }

    monkeypatch.setattr(zq, "CMDB", FakeCMDB)
    _stub_groups(monkeypatch, [{"id": 1, "name": "交易"}])
    rows = zq.load_selected_hosts(["u1"], {"user": "u", "team": 1})
    assert [row["inst_uuid"] for row in rows] == ["u1"]
    assert rows[0]["biz_name"] == "交易"


def test_load_selected_hosts_keeps_only_authorized_uuids(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    class FakeCMDB:
        def __init__(self, *args, **kwargs):
            pass

        def search_instances_batch(self, **kwargs):
            return {
                "result": True,
                "data": {
                    "u1": _host_entity("u1", "m1"),
                    "u2": _host_entity("u2", "m2"),
                },
            }

        def get_monitor_ids_by_inst_uuids(self, **kwargs):
            return {
                "result": True,
                "data": {"items": [{"inst_uuid": "u1", "model_id": "host", "monitor_id": "m1"}]},
                "message": "",
            }

    monkeypatch.setattr(zq, "CMDB", FakeCMDB)
    _stub_groups(monkeypatch)
    rows = zq.load_selected_hosts(["u1", "u2"], {"user": "u", "team": 1})
    assert [row["inst_uuid"] for row in rows] == ["u1"]
    assert rows[0]["monitor_id"] == "m1"
    assert rows[0]["host_name"] == "web-1"
    assert rows[0]["ip"] == "10.0.0.1"
    assert rows[0]["os_type"] == "1"
    assert rows[0]["node_id"] == "n1"
    assert rows[0]["zombie_whitelist"] == "no"


def test_load_selected_hosts_raises_when_monitor_ids_query_fails(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    class FakeCMDB:
        def __init__(self, *args, **kwargs):
            pass

        def search_instances_batch(self, **kwargs):
            return {
                "result": True,
                "data": {"u1": _host_entity("u1", "m1")},
            }

        def get_monitor_ids_by_inst_uuids(self, **kwargs):
            return {"result": False, "data": {"items": []}, "message": "无权"}

    monkeypatch.setattr(zq, "CMDB", FakeCMDB)
    _stub_groups(monkeypatch)
    with pytest.raises(zq.ZombieHostQueryError):
        zq.load_selected_hosts(["u1"], {"user": "u", "team": 1})


def test_load_hosts_for_systems_returns_rows_and_caps_expanded_count(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    captured = {}

    def fake_local(module_paths, method_name, **kwargs):
        captured["module_paths"] = module_paths
        captured["method_name"] = method_name
        captured["kwargs"] = kwargs
        return {
            "result": True,
            "data": {
                "items": [dict(HOST_U1)],
                "expanded_host_count": 1,
            },
            "message": "",
        }

    monkeypatch.setattr(zq, "run_inprocess_handler", fake_local)
    user_info = {"user": "u", "team": 1}
    rows = zq.load_hosts_for_systems(["s1"], user_info)
    assert captured["method_name"] == "list_monitored_hosts_for_systems"
    assert captured["module_paths"][0].endswith("zombie_overlay")
    assert captured["kwargs"]["system_uuids"] == ["s1"]
    assert captured["kwargs"]["user_info"] == user_info
    assert [row["inst_uuid"] for row in rows] == ["u1"]


def test_load_hosts_for_systems_raises_when_expanded_over_100(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    monkeypatch.setattr(
        zq,
        "run_inprocess_handler",
        lambda *a, **k: {"result": True, "data": {"items": [], "expanded_host_count": 101}, "message": ""},
    )
    with pytest.raises(ValueError, match="100"):
        zq.load_hosts_for_systems(["s1"], {"user": "u", "team": 1})


def test_load_hosts_for_systems_raises_when_cmdb_fails(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    monkeypatch.setattr(
        zq,
        "run_inprocess_handler",
        lambda *a, **k: {"result": False, "data": {"items": []}, "message": "down"},
    )
    with pytest.raises(zq.ZombieHostQueryError, match="down"):
        zq.load_hosts_for_systems(["s1"], {"user": "u", "team": 1})


def test_count_successful_logins_forwards_rfc3339_range(monkeypatch):
    from apps.monitor.services import zombie_host_query as zq

    captured = {}

    def fake_local(module_paths, method_name, **kwargs):
        captured["module_paths"] = module_paths
        captured["method_name"] = method_name
        captured["kwargs"] = kwargs
        return {"result": True, "data": []}

    monkeypatch.setattr(zq, "run_inprocess_handler", fake_local)
    time_range = ["2026-08-20T00:00:00.000Z", "2026-08-20T01:00:00.000Z"]
    hosts = [dict(HOST_U1)]
    out = zq.count_successful_logins(hosts, time_range, {"user": "u", "team": 1})
    assert out == {"result": True, "data": []}
    assert captured["method_name"] == "count_successful_logins_by_host"
    assert captured["module_paths"][0].endswith("zombie_overlay")
    assert captured["kwargs"]["time_range"] == time_range
    assert captured["kwargs"]["user_info"] == {"user": "u", "team": 1}
    assert captured["kwargs"]["hosts"] is hosts


def test_run_inprocess_handler_uses_first_callable_module(monkeypatch):
    from types import SimpleNamespace

    from apps.monitor.services import zombie_host_query as zq

    called = []

    monkeypatch.setattr(
        zq.importlib,
        "import_module",
        lambda path: SimpleNamespace(do=lambda **kwargs: called.append(path) or {"path": path, **kwargs}),
    )
    out = zq.run_inprocess_handler(("apps.overlay", "apps.nats"), "do", x=1)
    assert out == {"path": "apps.overlay", "x": 1}
    assert called == ["apps.overlay"]


def test_promql_and_series_use_logical_instance_id(monkeypatch):
    storage_id = "('host-ecom-inventory-01',)"
    logical_id = "host-ecom-inventory-01"
    host = {**HOST_U1, "monitor_id": storage_id}
    monkeypatch.setattr(nm, "load_selected_hosts", lambda inst_uuids, user_info: [host])
    _patch_scope(monkeypatch, {storage_id: SimpleNamespace(id=storage_id)})
    queried = []

    class FakeVM:
        def query(self, q, *a, **k):
            queried.append(q)
            return {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": logical_id},
                            "value": [1, "3.5"],
                        }
                    ]
                },
            }

    monkeypatch.setattr(nm, "VictoriaMetricsAPI", FakeVM)
    monkeypatch.setattr(
        nm,
        "count_successful_logins",
        lambda hosts, *a, **k: {"result": True, "data": []},
    )
    out = nm.get_zombie_host_report(
        inst_uuids=["u1"],
        time=10080,
        user_info={"user": "u", "team": 1},
        **_unbounded_thresholds(),
    )
    assert out["result"] is True
    assert queried
    joined = "\n".join(queried)
    assert "host-ecom-inventory-01" in joined.replace("\\", "")
    assert storage_id not in joined
    row = out["data"]["items"][0]
    assert row["monitor_id"] == storage_id
    assert row["cpu_avg"] == 3.5
    assert row["cpu_max"] == 3.5

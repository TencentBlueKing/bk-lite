"""WeCenter 回归：协同办公树按类型摊进应用上下文，锁口径。"""

import pytest

from apps.cmdb.models.ci_context import CmdbCiContext
from apps.cmdb.services.ci_context import recompute_application
from apps.cmdb.tests.test_ci_context_recompute import _bind, _rows, edge, inst

pytestmark = pytest.mark.django_db

CORE_MEMBERS = ("host-1", "vm-1", "mysql-1", "redis-1", "rabbit-1")
ABSENT = ("app-wecenter", "sys-office", "rack-1", "sw-1")


def _wecenter(monkeypatch, *, with_tidb=False):
    """system 协同办公 contains WeCenter；主机 run 虚机和中间件；另有一条机柜边。"""
    system = inst("sys-office", "system", inst_name="协同办公")
    app = inst("app-wecenter", "application", inst_name="WeCenter")
    host = inst("host-1", "host")
    vm = inst("vm-1", "vm")
    mysql = inst("mysql-1", "mysql")
    redis = inst("redis-1", "redis")
    rabbit = inst("rabbit-1", "rabbitmq")
    rack = inst("rack-1", "rack")
    switch = inst("sw-1", "switch")
    instances = [system, app, host, vm, mysql, redis, rabbit, rack, switch]
    edges = [
        edge("contains", system, app),
        edge("run", app, host),
        edge("run", host, vm, model_asst_id="host_run_vm"),
        edge("run", host, mysql, model_asst_id="host_run_mysql"),
        edge("run", host, redis, model_asst_id="host_run_redis"),
        edge("run", host, rabbit, model_asst_id="host_run_rabbitmq"),
        edge("contains", rack, switch, model_asst_id="rack_contains_switch"),
    ]
    if with_tidb:
        tidb = inst("tidb-1", "tidb_extra")
        instances.append(tidb)
        edges.append(edge("connect", app, tidb, model_asst_id="application_connect_tidb_extra"))
    graph = _bind(monkeypatch, instances, edges)
    assert all(item.get("model_asst_id") != "application_connect_mysql" for item in graph.edges)
    return graph


def _by_ci(root_uuid="app-wecenter"):
    return {row.ci_uuid: row for row in _rows(root_uuid)}


def test_wecenter_core_tree_writes_five_members(monkeypatch):
    """无 tidb：5 行。主机 L1，虚机/MySQL/Redis/Rabbit L2。MySQL 没有 connect 仍进表。"""
    _wecenter(monkeypatch)

    recompute_application("app-wecenter")

    rows = _by_ci()
    assert set(rows) == set(CORE_MEMBERS)
    assert len(rows) == 5
    host = rows["host-1"]
    assert host.layer == 1
    assert not host.via_uuid
    assert host.ci_model == "host"
    assert host.model_asst_id == "application_run_host"
    assert host.system_uuid == "sys-office"
    for ci_uuid, model in (
        ("vm-1", "vm"),
        ("mysql-1", "mysql"),
        ("redis-1", "redis"),
        ("rabbit-1", "rabbitmq"),
    ):
        row = rows[ci_uuid]
        assert row.layer == 2
        assert row.via_uuid == "host-1"
        assert row.ci_model == model
        assert row.model_asst_id == f"host_run_{model}"
        assert row.system_uuid == "sys-office"
    assert "application_connect_mysql" not in {row.model_asst_id for row in rows.values()}
    assert not CmdbCiContext.objects.filter(ci_uuid__in=ABSENT).exists()
    assert not CmdbCiContext.objects.filter(model_asst_id="rack_contains_switch").exists()
    assert not any(row.ci_model in {"application", "system", "rack", "switch"} for row in rows.values())


def test_wecenter_drop_redis_edge_removes_only_redis(monkeypatch):
    """摘掉 host_run_redis 再重算，只少 Redis，其余成员还在。"""
    graph = _wecenter(monkeypatch)
    recompute_application("app-wecenter")
    assert {row.ci_uuid for row in _rows("app-wecenter")} == set(CORE_MEMBERS)

    graph.edges = [item for item in graph.edges if item.get("model_asst_id") != "host_run_redis"]
    recompute_application("app-wecenter")

    rows = _by_ci()
    assert set(rows) == {"host-1", "vm-1", "mysql-1", "rabbit-1"}
    assert len(rows) == 4
    assert "redis-1" not in rows
    assert rows["host-1"].layer == 1
    assert not rows["host-1"].via_uuid
    for ci_uuid in ("vm-1", "mysql-1", "rabbit-1"):
        assert rows[ci_uuid].layer == 2
        assert rows[ci_uuid].via_uuid == "host-1"
        assert rows[ci_uuid].system_uuid == "sys-office"
    assert rows["host-1"].system_uuid == "sys-office"
    assert not CmdbCiContext.objects.filter(ci_uuid="redis-1", root_uuid="app-wecenter").exists()


def test_wecenter_tidb_extra_connect_is_layer1_without_override(monkeypatch):
    """自建 tidb_extra 只靠 application_connect，layer 1，via 为空，不用 include 覆盖。"""
    graph = _wecenter(monkeypatch, with_tidb=True)
    connect = [item for item in graph.edges if item.get("model_asst_id") == "application_connect_tidb_extra"]
    assert len(connect) == 1
    assert connect[0]["asst_id"] == "connect"
    assert "context_link" not in connect[0]

    recompute_application("app-wecenter")

    rows = _by_ci()
    assert set(rows) == set(CORE_MEMBERS) | {"tidb-1"}
    assert len(rows) == 6
    tidb = rows["tidb-1"]
    assert tidb.layer == 1
    assert not tidb.via_uuid
    assert tidb.ci_model == "tidb_extra"
    assert tidb.model_asst_id == "application_connect_tidb_extra"
    assert tidb.system_uuid == "sys-office"
    assert rows["mysql-1"].layer == 2
    assert rows["mysql-1"].model_asst_id == "host_run_mysql"

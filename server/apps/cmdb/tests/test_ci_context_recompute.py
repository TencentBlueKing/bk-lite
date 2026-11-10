"""从应用正向最多两跳重算 ci_context。图访问走 MemoryGraph，不连真实库。"""

import pytest

from apps.cmdb.models.ci_context import CmdbCiContext
from apps.cmdb.services.ci_context import recompute_application
from apps.cmdb.services.ci_context_policy import CONTEXT_APPLICATION

pytestmark = pytest.mark.django_db


class MemoryGraph:
    def __init__(self, instances):
        self.instances = list(instances)
        self.edges = []
        self.model_edges = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, label, conditions, **kwargs):
        rows = list(self.instances)
        for condition in conditions or []:
            field, op, value = condition.get("field"), condition.get("type"), condition.get("value")
            if op in ("str=", None) or op == "=":
                rows = [r for r in rows if r.get(field) == value]
            elif op == "str[]":
                rows = [r for r in rows if r.get(field) in value]
        return rows, len(rows)

    def query_edge(self, label, conditions, param_type="AND", return_entity=False):
        from apps.cmdb.constants.constants import MODEL_ASSOCIATION

        pool = self.model_edges if label == MODEL_ASSOCIATION else self.edges

        def matches(edge):
            props = edge.get("edge", edge)
            checks = []
            for condition in conditions or []:
                checks.append(props.get(condition["field"]) == condition["value"] or edge.get(condition["field"]) == condition["value"])
            if not checks:
                return True
            return all(checks) if param_type != "OR" else any(checks)

        hits = [edge for edge in pool if matches(edge)]
        if not return_entity:
            return [edge.get("edge", edge) for edge in hits]
        by_uuid = {row.get("inst_uuid"): row for row in self.instances}
        result = []
        for edge in hits:
            props = edge.get("edge", edge)
            src_uuid = props.get("src_inst_uuid")
            dst_uuid = props.get("dst_inst_uuid")
            result.append(
                {
                    "edge": props,
                    "src": edge.get("src") or by_uuid.get(src_uuid) or {"inst_uuid": src_uuid, "model_id": props.get("src_model_id")},
                    "dst": edge.get("dst") or by_uuid.get(dst_uuid) or {"inst_uuid": dst_uuid, "model_id": props.get("dst_model_id")},
                }
            )
        return result


def inst(uuid, model, ip="", org=None, **extra):
    row = {"inst_uuid": uuid, "model_id": model, "ip_addr": ip, "organization": org or [1]}
    row.update(extra)
    return row


def edge(asst_id, src, dst, model_asst_id=None, link=None):
    src = src if isinstance(src, dict) else inst(src, "?")
    dst = dst if isinstance(dst, dict) else inst(dst, "?")
    props = {
        "asst_id": asst_id,
        "model_asst_id": model_asst_id or f"{src['model_id']}_{asst_id}_{dst['model_id']}",
        "src_inst_uuid": src["inst_uuid"],
        "dst_inst_uuid": dst["inst_uuid"],
        "src_model_id": src["model_id"],
        "dst_model_id": dst["model_id"],
    }
    if link is not None:
        props["context_link"] = link
    return props


def _bind(monkeypatch, instances, edges):
    graph = MemoryGraph(instances)
    graph.edges = list(edges)
    monkeypatch.setattr("apps.cmdb.services.ci_context.GraphClient", lambda *a, **k: graph)
    return graph


def _member(**overrides):
    data = dict(
        ci_uuid="old-ci",
        context=CONTEXT_APPLICATION,
        root_uuid="app-wecenter",
        root_model="application",
        ci_model="host",
        ip_addr="9.9.9.9",
        organization=[9],
        system_uuid=None,
        layer=1,
        via_uuid="stale-via",
        model_asst_id="stale",
        payload={"old": True},
    )
    data.update(overrides)
    return CmdbCiContext.objects.create(**data)


def _rows(root_uuid):
    return list(CmdbCiContext.objects.filter(root_uuid=root_uuid, context=CONTEXT_APPLICATION).order_by("ci_uuid"))


def test_wecenter_tree_writes_host_l1_and_middleware_l2(monkeypatch):
    """system contains app; app run host; host run vm/mysql/redis/rabbitmq → 5 行。"""
    system = inst("sys-1", "system", ip="10.0.0.1", org=[1])
    app = inst("app-wecenter", "application", ip="10.0.0.2", org=[1])
    host = inst("host-1", "host", ip="10.1.0.1", org=[7])
    vm = inst("vm-1", "vm", ip="10.1.0.2", org=[7])
    mysql = inst("mysql-1", "mysql", ip="10.1.0.3", org=[8])
    redis = inst("redis-1", "redis", ip="10.1.0.4", org=[8])
    rabbit = inst("rabbit-1", "rabbitmq", ip="10.1.0.5", org=[9])
    nginx = inst("nginx-1", "nginx", ip="10.1.0.6", org=[9])
    _bind(
        monkeypatch,
        [system, app, host, vm, mysql, redis, rabbit, nginx],
        [
            edge("contains", system, app),
            edge("run", app, host),
            edge("run", host, vm),
            edge("run", host, mysql),
            edge("run", host, redis),
            edge("run", host, rabbit),
            edge("run", mysql, nginx),
        ],
    )

    recompute_application(" app-wecenter ")

    rows = {row.ci_uuid: row for row in _rows("app-wecenter")}
    assert set(rows) == {"host-1", "vm-1", "mysql-1", "redis-1", "rabbit-1"}
    assert rows["host-1"].layer == 1
    assert not rows["host-1"].via_uuid
    assert rows["host-1"].model_asst_id == "application_run_host"
    assert rows["host-1"].ci_model == "host"
    assert rows["host-1"].ip_addr == "10.1.0.1"
    assert rows["host-1"].organization == [7]
    assert rows["host-1"].root_model == "application"
    assert rows["host-1"].payload == {}
    assert rows["host-1"].system_uuid == "sys-1"
    for ci_uuid, model, ip_addr, organization in (
        ("vm-1", "vm", "10.1.0.2", [7]),
        ("mysql-1", "mysql", "10.1.0.3", [8]),
        ("redis-1", "redis", "10.1.0.4", [8]),
        ("rabbit-1", "rabbitmq", "10.1.0.5", [9]),
    ):
        row = rows[ci_uuid]
        assert row.layer == 2
        assert row.via_uuid == "host-1"
        assert row.model_asst_id == f"host_run_{model}"
        assert row.ci_model == model
        assert row.ip_addr == ip_addr
        assert row.organization == organization
        assert row.system_uuid == "sys-1"
        assert row.payload == {}
    assert not CmdbCiContext.objects.filter(ci_uuid__in=["app-wecenter", "sys-1", "nginx-1"]).exists()


def test_host_run_mysql_and_redis_are_one_rule(monkeypatch):
    """两条 host_run_* 都是 layer=2，via=host。"""
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1")
    mysql = inst("mysql-1", "mysql", ip="10.1.0.3")
    redis = inst("redis-1", "redis", ip="10.1.0.4")
    _bind(
        monkeypatch,
        [app, host, mysql, redis],
        [
            edge("run", app, host),
            edge("run", host, mysql, model_asst_id="host_run_mysql"),
            edge("run", host, redis, model_asst_id="host_run_redis"),
        ],
    )

    recompute_application("app-wecenter")

    rows = {row.ci_uuid: row for row in _rows("app-wecenter")}
    assert rows["mysql-1"].layer == 2
    assert rows["mysql-1"].via_uuid == "host-1"
    assert rows["mysql-1"].model_asst_id == "host_run_mysql"
    assert rows["redis-1"].layer == 2
    assert rows["redis-1"].via_uuid == "host-1"
    assert rows["redis-1"].model_asst_id == "host_run_redis"


def test_missing_application_connect_mysql_still_gets_mysql_via_host(monkeypatch):
    """没有 application_connect_mysql 时，MySQL 仍因 host run 进表。"""
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host")
    mysql = inst("mysql-1", "mysql", ip="10.1.0.3", org=[3])
    _bind(
        monkeypatch,
        [app, host, mysql],
        [edge("run", app, host), edge("run", host, mysql)],
    )

    recompute_application("app-wecenter")

    rows = {row.ci_uuid: row for row in _rows("app-wecenter")}
    assert set(rows) == {"host-1", "mysql-1"}
    assert rows["mysql-1"].layer == 2
    assert rows["mysql-1"].via_uuid == "host-1"
    assert rows["mysql-1"].model_asst_id == "host_run_mysql"
    assert "application_connect_mysql" not in {row.model_asst_id for row in rows.values()}


def test_recompute_skips_switch_and_belong(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host")
    switch = inst("sw-1", "switch")
    account = inst("acc-1", "aliyun_account")
    _bind(
        monkeypatch,
        [app, host, switch, account],
        [
            edge("run", app, switch),
            edge("run", app, host),
            edge("belong", host, account),
        ],
    )

    recompute_application("app-wecenter")

    rows = _rows("app-wecenter")
    assert [row.ci_uuid for row in rows] == ["host-1"]
    assert rows[0].layer == 1


def test_recompute_replaces_stale_rows_for_that_application_only(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.1", org=[4])
    _bind(monkeypatch, [app, host], [edge("run", app, host)])
    _member(ci_uuid="old-ci", root_uuid="app-wecenter")
    kept = _member(ci_uuid="host-x", root_uuid="other-app", via_uuid=None, payload={"keep": True})

    recompute_application("app-wecenter")

    assert not CmdbCiContext.objects.filter(root_uuid="app-wecenter", ci_uuid="old-ci").exists()
    current = {row.ci_uuid: row for row in _rows("app-wecenter")}
    assert set(current) == {"host-1"}
    assert current["host-1"].layer == 1
    assert not current["host-1"].via_uuid
    kept.refresh_from_db()
    assert kept.root_uuid == "other-app"
    assert kept.ci_uuid == "host-x"
    assert kept.payload == {"keep": True}


def test_legacy_model_asst_id_run(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host", ip="10.1.0.8")
    _bind(monkeypatch, [app, host], [edge("run", app, host, model_asst_id="run")])

    recompute_application("app-wecenter")

    rows = _rows("app-wecenter")
    assert [row.ci_uuid for row in rows] == ["host-1"]
    assert rows[0].layer == 1
    assert rows[0].model_asst_id == "run"
    assert not rows[0].via_uuid


def test_missing_application_deletes_its_rows(monkeypatch):
    _bind(monkeypatch, [inst("host-1", "host")], [])
    _member(ci_uuid="old-ci", root_uuid="app-gone")
    kept = _member(ci_uuid="host-x", root_uuid="other-app")

    recompute_application("app-gone")

    assert not CmdbCiContext.objects.filter(root_uuid="app-gone").exists()
    assert CmdbCiContext.objects.filter(pk=kept.pk, root_uuid="other-app").exists()


def test_connect_custom_model_is_layer1(monkeypatch):
    app = inst("app-wecenter", "application")
    tidb = inst("tidb-1", "tidb_extra", ip="10.2.0.1", org=[6])
    _bind(monkeypatch, [app, tidb], [edge("connect", app, tidb)])

    recompute_application("app-wecenter")

    rows = _rows("app-wecenter")
    assert [row.ci_uuid for row in rows] == ["tidb-1"]
    assert rows[0].layer == 1
    assert not rows[0].via_uuid
    assert rows[0].ci_model == "tidb_extra"
    assert rows[0].model_asst_id == "application_connect_tidb_extra"
    assert rows[0].ip_addr == "10.2.0.1"
    assert rows[0].organization == [6]
    assert rows[0].system_uuid is None


def test_l1_wins_over_l2_for_same_ci(monkeypatch):
    app = inst("app-wecenter", "application")
    host = inst("host-1", "host")
    mysql = inst("mysql-1", "mysql", ip="10.3.0.1")
    _bind(
        monkeypatch,
        [app, host, mysql],
        [
            edge("connect", app, mysql),
            edge("run", app, host),
            edge("run", host, mysql),
        ],
    )

    recompute_application("app-wecenter")

    rows = {row.ci_uuid: row for row in _rows("app-wecenter")}
    assert set(rows) == {"host-1", "mysql-1"}
    assert rows["mysql-1"].layer == 1
    assert not rows["mysql-1"].via_uuid
    assert rows["mysql-1"].model_asst_id == "application_connect_mysql"
    assert rows["host-1"].layer == 1

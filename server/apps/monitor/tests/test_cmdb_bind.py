"""CMDB 手绑：按 ID 写 cmdb_id、列候选、按 expected 清除。

status 约定（RPC 调用方按字段分支，不靠异常）：
- bind 成功：{status: "ok", monitor_id, cmdb_id}
- 占用：{status: "occupied", occupied_cmdb_id}
- 实例缺失 / 已删 / 组织越权：{status: "not_found"}
- 对象类型不符：{status: "type_mismatch"}
- clear 期望不符：{status: "mismatch"}
- clear 已空或清除成功：{status: "ok", ...}
"""

import logging

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject

pytestmark = pytest.mark.django_db

CANDIDATE_KEYS = {"id", "name", "ip", "object_name", "cmdb_id"}
BIND_OK_TEMPLATE = "event=cmdb_bind_ok monitor_id=%s cmdb_id=%s"
BIND_OCCUPIED_TEMPLATE = "event=cmdb_bind_occupied monitor_id=%s occupied_cmdb_id=%s"


def _object(name="Host"):
    obj, _ = MonitorObject.objects.get_or_create(
        name=name,
        defaults={"display_name": name, "level": "base"},
    )
    return obj


def _instance(
    *,
    pk,
    name,
    object_name="Host",
    ip=None,
    cmdb_id=None,
    node_id=None,
    org=1,
    is_deleted=False,
):
    inst = MonitorInstance.objects.create(
        id=pk,
        name=name,
        monitor_object=_object(object_name),
        ip=ip,
        cmdb_id=cmdb_id,
        node_id=node_id,
        is_deleted=is_deleted,
    )
    if org is not None:
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=org)
    return inst


def _assert_candidate_row(row):
    assert set(row.keys()) == CANDIDATE_KEYS
    assert row["name"]
    assert row["id"]
    assert "object_name" in row
    assert "ip" in row
    assert "cmdb_id" in row


def test_bind_occupied_when_target_already_has_other_cmdb_id():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    inst = _instance(pk="m-occ", name="web-1", cmdb_id="ci-old")
    result = bind_cmdb_id("m-occ", "ci-new", "Host", [1])

    assert result == {"status": "occupied", "occupied_cmdb_id": "ci-old"}
    inst.refresh_from_db()
    assert inst.cmdb_id == "ci-old"
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1


def test_bind_type_mismatch_host_vs_docker_container():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    inst = _instance(pk="m-docker", name="ctr-1", object_name="Docker Container")
    result = bind_cmdb_id("m-docker", "ci-1", "Host", [1])

    assert result == {"status": "type_mismatch"}
    inst.refresh_from_db()
    assert inst.cmdb_id is None


def test_candidates_include_name_not_id_only():
    from apps.monitor.services.cmdb_bind import list_cmdb_bind_candidates

    _instance(pk="m-named", name="prod-web", ip="10.0.0.8")
    rows = list_cmdb_bind_candidates("Host", "", [1])

    assert len(rows) == 1
    _assert_candidate_row(rows[0])
    assert rows[0]["id"] == "m-named"
    assert rows[0]["name"] == "prod-web"
    assert rows[0]["ip"] == "10.0.0.8"
    assert rows[0]["object_name"] == "Host"
    assert rows[0]["cmdb_id"] is None


def test_candidates_query_matches_name_and_ip():
    from apps.monitor.services.cmdb_bind import list_cmdb_bind_candidates

    _instance(pk="m-a", name="alpha-web", ip="10.1.2.3")
    _instance(pk="m-b", name="beta-db", ip="10.9.9.9")

    by_name = list_cmdb_bind_candidates("Host", "alpha", [1])
    by_ip = list_cmdb_bind_candidates("Host", "10.1.2", [1])
    miss = list_cmdb_bind_candidates("Host", "no-such", [1])

    assert [row["id"] for row in by_name] == ["m-a"]
    _assert_candidate_row(by_name[0])
    assert [row["id"] for row in by_ip] == ["m-a"]
    _assert_candidate_row(by_ip[0])
    assert miss == []


def test_candidates_exclude_deleted_instances():
    from apps.monitor.services.cmdb_bind import list_cmdb_bind_candidates

    _instance(pk="m-live", name="live-host")
    _instance(pk="m-gone", name="gone-host", is_deleted=True)
    rows = list_cmdb_bind_candidates("Host", "", [1])

    assert [row["id"] for row in rows] == ["m-live"]
    _assert_candidate_row(rows[0])


def test_org_out_of_scope_not_listed_and_bind_not_found():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id, list_cmdb_bind_candidates

    _instance(pk="m-foreign", name="other-org", org=2)
    rows = list_cmdb_bind_candidates("Host", "", [1])
    result = bind_cmdb_id("m-foreign", "ci-1", "Host", [1])

    assert rows == []
    assert result == {"status": "not_found"}


def test_bind_same_cmdb_id_is_idempotent_ok():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    inst = _instance(pk="m-same", name="web-1", cmdb_id="ci-keep")
    result = bind_cmdb_id("m-same", "ci-keep", "Host", [1])

    assert result == {"status": "ok", "monitor_id": "m-same", "cmdb_id": "ci-keep"}
    inst.refresh_from_db()
    assert inst.cmdb_id == "ci-keep"


def test_bind_refuses_steal_when_another_instance_holds_cmdb_id():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    target = _instance(pk="m-target", name="free-host")
    occupier = _instance(pk="m-holder", name="taken-host", cmdb_id="ci-taken")

    result = bind_cmdb_id("m-target", "ci-taken", "Host", [1])

    assert result == {"status": "occupied", "occupied_cmdb_id": "ci-taken"}
    target.refresh_from_db()
    occupier.refresh_from_db()
    assert target.cmdb_id is None
    assert occupier.cmdb_id == "ci-taken"


def test_clear_cmdb_id_only_when_expected_matches_and_keeps_node_id():
    from apps.monitor.services.cmdb_bind import clear_cmdb_id

    inst = _instance(pk="m-clear", name="web-1", cmdb_id="ci-1", node_id="n-keep")

    mismatch = clear_cmdb_id("m-clear", "ci-other", [1])
    inst.refresh_from_db()
    assert mismatch == {"status": "mismatch"}
    assert inst.cmdb_id == "ci-1"
    assert inst.node_id == "n-keep"

    ok = clear_cmdb_id("m-clear", "ci-1", [1])
    inst.refresh_from_db()
    assert ok == {"status": "ok", "monitor_id": "m-clear", "cmdb_id": None}
    assert inst.cmdb_id is None
    assert inst.node_id == "n-keep"

    again = clear_cmdb_id("m-clear", "ci-1", [1])
    inst.refresh_from_db()
    assert again["status"] == "ok"
    assert inst.cmdb_id is None
    assert inst.node_id == "n-keep"


def test_bind_success_writes_cmdb_id_without_creating_or_touching_node():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    inst = _instance(pk="m-ok", name="web-1", node_id="n-keep")
    result = bind_cmdb_id("m-ok", "ci-new", "Host", [1])

    assert result == {"status": "ok", "monitor_id": "m-ok", "cmdb_id": "ci-new"}
    inst.refresh_from_db()
    assert inst.cmdb_id == "ci-new"
    assert inst.node_id == "n-keep"
    assert MonitorInstance.objects.filter(is_deleted=False).count() == 1


def test_bind_missing_or_deleted_is_not_found():
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    _instance(pk="m-del", name="gone", is_deleted=True)
    assert bind_cmdb_id("missing", "ci-1", "Host", [1]) == {"status": "not_found"}
    assert bind_cmdb_id("m-del", "ci-1", "Host", [1]) == {"status": "not_found"}
    assert MonitorInstance.objects.filter(pk="m-created-by-bind").exists() is False


def test_clear_not_found_when_missing_deleted_or_org_out_of_scope():
    from apps.monitor.services.cmdb_bind import clear_cmdb_id

    _instance(pk="m-del", name="gone", cmdb_id="ci-1", is_deleted=True)
    _instance(pk="m-foreign", name="other", cmdb_id="ci-2", org=2)

    assert clear_cmdb_id("missing", "ci-1", [1]) == {"status": "not_found"}
    assert clear_cmdb_id("m-del", "ci-1", [1]) == {"status": "not_found"}
    assert clear_cmdb_id("m-foreign", "ci-2", [1]) == {"status": "not_found"}


def test_candidates_empty_orgs_or_empty_query_still_respects_scope():
    from apps.monitor.services.cmdb_bind import list_cmdb_bind_candidates

    _instance(pk="m-z", name="zeta")
    _instance(pk="m-a", name="alpha")

    assert list_cmdb_bind_candidates("Host", "", []) == []
    assert list_cmdb_bind_candidates("Host", None, None) == []
    rows = list_cmdb_bind_candidates("Host", "", [1], limit=50)
    assert [row["id"] for row in rows] == ["m-a", "m-z"]
    for row in rows:
        _assert_candidate_row(row)
    assert list_cmdb_bind_candidates("Docker Container", "", [1]) == []


def test_candidates_limit_clamped():
    from apps.monitor.services.cmdb_bind import list_cmdb_bind_candidates

    _instance(pk="m-1", name="a-host")
    _instance(pk="m-2", name="b-host")
    _instance(pk="m-3", name="c-host")

    assert len(list_cmdb_bind_candidates("Host", "", [1], limit=2)) == 2
    assert len(list_cmdb_bind_candidates("Host", "", [1], limit=999)) == 3


def test_bind_and_clear_logs_lifecycle_without_payload(caplog):
    from apps.monitor.services.cmdb_bind import bind_cmdb_id

    sentinel = "super-secret-password-token"
    inst = _instance(pk="m-log", name="web-1")
    caplog.set_level(logging.INFO, logger="monitor")

    result = bind_cmdb_id("m-log", "ci-log", "Host", [1])
    occupied = bind_cmdb_id("m-log", "ci-other", "Host", [1])

    assert result["status"] == "ok"
    assert occupied["status"] == "occupied"
    ok_records = [record for record in caplog.records if record.msg == BIND_OK_TEMPLATE]
    occupied_records = [record for record in caplog.records if record.msg == BIND_OCCUPIED_TEMPLATE]
    assert len(ok_records) == 1
    assert ok_records[0].args == ("m-log", "ci-log")
    assert "ci-log" in ok_records[0].getMessage()
    assert occupied_records
    assert occupied_records[0].args[0] == "m-log"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in rendered
    assert "password" not in rendered.lower()
    inst.refresh_from_db()
    assert inst.cmdb_id == "ci-log"


def test_nats_handlers_call_through_service():
    from apps.monitor.nats import monitor as nm

    _instance(pk="m-nats", name="nats-host", ip="10.2.2.2")
    rows = nm.monitor_list_cmdb_bind_candidates({"object_name": "Host", "query": "nats", "allowed_org_ids": [1]})
    bound = nm.monitor_bind_cmdb_id({"monitor_id": "m-nats", "cmdb_id": "ci-nats", "object_name": "Host", "allowed_org_ids": [1]})
    cleared = nm.monitor_clear_cmdb_id({"monitor_id": "m-nats", "expected_cmdb_id": "ci-nats", "allowed_org_ids": [1]})

    assert len(rows) == 1
    _assert_candidate_row(rows[0])
    assert rows[0]["name"] == "nats-host"
    assert bound == {"status": "ok", "monitor_id": "m-nats", "cmdb_id": "ci-nats"}
    assert cleared == {"status": "ok", "monitor_id": "m-nats", "cmdb_id": None}


@pytest.mark.unit
def test_rpc_wrappers_use_ingest_client_params_envelope(monkeypatch):
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    from apps.rpc.monitor import Monitor

    class _Recorder:
        def __init__(self):
            self.calls = []

        def run(self, method_name, *args, **kwargs):
            self.calls.append((method_name, args, kwargs))
            return {"status": "ok"}

    rpc = Monitor(is_local_client=False)
    rec = _Recorder()
    rpc.ingest_client = rec

    rpc.list_cmdb_bind_candidates(object_name="Host", query="web", allowed_org_ids=[1], limit=50)
    rpc.bind_cmdb_id(monitor_id="m-1", cmdb_id="ci-1", object_name="Host", allowed_org_ids=[1])
    rpc.clear_cmdb_id(monitor_id="m-1", expected_cmdb_id="ci-1", allowed_org_ids=[1])

    assert rec.calls[0] == (
        "monitor_list_cmdb_bind_candidates",
        (),
        {"params": {"object_name": "Host", "query": "web", "allowed_org_ids": [1], "limit": 50}},
    )
    assert rec.calls[1] == (
        "monitor_bind_cmdb_id",
        (),
        {"params": {"monitor_id": "m-1", "cmdb_id": "ci-1", "object_name": "Host", "allowed_org_ids": [1]}},
    )
    assert rec.calls[2] == (
        "monitor_clear_cmdb_id",
        (),
        {"params": {"monitor_id": "m-1", "expected_cmdb_id": "ci-1", "allowed_org_ids": [1]}},
    )

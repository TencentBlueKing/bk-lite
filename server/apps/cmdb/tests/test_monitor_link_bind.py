"""CMDB 详情手绑 / 解绑 / 候选：服务层与 instance view。"""

import json
import logging

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.monitor_link import MonitorLinkService
from apps.cmdb.views.instance import InstanceViewSet

QUERY_PATH = "apps.cmdb.services.monitor_link.InstanceManage.query_entity_by_uuid"
UPDATE_UUID_PATH = "apps.cmdb.services.monitor_link.InstanceManage.instance_update_by_uuid"
BACKFILL_PATH = "apps.cmdb.services.monitor_link.CmdbToMonitorPushService._backfill_monitor_id"
MONITOR_PATH = "apps.cmdb.services.monitor_link.Monitor"
VIEWS = "apps.cmdb.views.instance"

INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
OCCUPIED_UUID = "a18f0c2e-4b7d-4e91-9c3a-7f2b1d4e5a60"
ACTOR_SCOPE = {"allowed_org_ids": [1], "operator": "alice"}

UNBIND_FAILED_TEMPLATE = "event=cmdb_monitor_link_unbind_failed inst_uuid=%s failed_stage=%s error_type=%s"


def _entity(inst_uuid=INST_UUID, *, model_id="host", monitor_id=None, inst_name=None, node_id="node-keep", **extra):
    row = {
        "_id": extra.pop("_id", 101),
        "inst_uuid": inst_uuid,
        "model_id": model_id,
        "inst_name": inst_name or f"name-{inst_uuid[:8]}",
        "organization": [1],
        "ip_addr": "10.0.0.8",
        "node_id": node_id,
    }
    if monitor_id is not None:
        row["monitor_id"] = monitor_id
    row.update(extra)
    return row


def _monitor(mocker, **methods):
    monitor = mocker.Mock()
    for name, value in methods.items():
        getattr(monitor, name).return_value = value
    mocker.patch(MONITOR_PATH, return_value=monitor)
    return monitor


# ---------------------------------------------------------------------------
# service: bind
# ---------------------------------------------------------------------------


def test_bind_occupied_includes_occupier_instance_name(mocker):
    entities = {
        INST_UUID: _entity(INST_UUID, inst_name="ci-self"),
        OCCUPIED_UUID: _entity(OCCUPIED_UUID, inst_name="occupied-host", _id=202),
    }
    mocker.patch(QUERY_PATH, side_effect=lambda uuid: entities.get(uuid))
    monitor = _monitor(
        mocker,
        bind_cmdb_id={"status": "occupied", "occupied_cmdb_id": OCCUPIED_UUID},
    )
    backfill = mocker.patch(BACKFILL_PATH)
    update = mocker.patch(UPDATE_UUID_PATH)

    result = MonitorLinkService.bind(INST_UUID, "m-occ", ACTOR_SCOPE)

    assert result["status"] == "occupied"
    assert result["occupied_inst_name"] == "occupied-host"
    assert result["occupied_inst_uuid"] == OCCUPIED_UUID
    monitor.bind_cmdb_id.assert_called_once_with(
        monitor_id="m-occ",
        cmdb_id=INST_UUID,
        object_name="Host",
        allowed_org_ids=[1],
    )
    backfill.assert_not_called()
    update.assert_not_called()


def test_bind_backfill_failure_clears_monitor_cmdb_id(mocker):
    entity = _entity(INST_UUID)
    mocker.patch(QUERY_PATH, return_value=entity)
    monitor = _monitor(mocker, bind_cmdb_id={"status": "ok", "monitor_id": "m-new", "cmdb_id": INST_UUID})
    mocker.patch(BACKFILL_PATH, return_value=entity)
    update = mocker.patch(UPDATE_UUID_PATH)

    result = MonitorLinkService.bind(INST_UUID, "m-new", ACTOR_SCOPE)

    assert result["status"] == "failed"
    assert result["failed_side"] == "cmdb"
    monitor.clear_cmdb_id.assert_called_once_with(
        monitor_id="m-new",
        expected_cmdb_id=INST_UUID,
        allowed_org_ids=[1],
    )
    update.assert_not_called()


def test_bind_same_monitor_id_is_idempotent(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID, monitor_id="m-keep"))
    monitor = _monitor(mocker)
    backfill = mocker.patch(BACKFILL_PATH)

    result = MonitorLinkService.bind(INST_UUID, "m-keep", ACTOR_SCOPE)

    assert result["status"] == "ok"
    assert result["monitor_id"] == "m-keep"
    monitor.bind_cmdb_id.assert_not_called()
    backfill.assert_not_called()


def test_bind_different_monitor_without_confirm_requires_confirm(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID, monitor_id="m-old"))
    monitor = _monitor(mocker)

    result = MonitorLinkService.bind(INST_UUID, "m-new", ACTOR_SCOPE, confirm=False)

    assert result["status"] == "confirm_required"
    assert result["monitor_id"] == "m-old"
    monitor.bind_cmdb_id.assert_not_called()


def test_bind_confirm_unbinds_then_binds(mocker):
    linked = _entity(INST_UUID, monitor_id="m-old")
    cleared = _entity(INST_UUID, monitor_id="")
    mocker.patch(QUERY_PATH, side_effect=[linked, cleared])
    unbind = mocker.patch.object(
        MonitorLinkService,
        "unbind",
        return_value={"status": "ok", "failed_side": None},
    )
    monitor = _monitor(mocker, bind_cmdb_id={"status": "ok", "monitor_id": "m-new", "cmdb_id": INST_UUID})
    backfill = mocker.patch(BACKFILL_PATH, return_value={**cleared, "monitor_id": "m-new"})

    result = MonitorLinkService.bind(INST_UUID, "m-new", ACTOR_SCOPE, confirm=True)

    assert result["status"] == "ok"
    assert result["monitor_id"] == "m-new"
    unbind.assert_called_once_with(INST_UUID, ACTOR_SCOPE)
    monitor.bind_cmdb_id.assert_called_once()
    backfill.assert_called_once()


# ---------------------------------------------------------------------------
# service: unbind
# ---------------------------------------------------------------------------


def test_unbind_clears_cmdb_monitor_id_and_does_not_touch_node_id(mocker):
    entity = _entity(INST_UUID, monitor_id="m-linked", node_id="node-keep")
    mocker.patch(QUERY_PATH, return_value=entity)
    monitor = _monitor(mocker, ingest_from_source={"id": "m-linked", "updated": True})
    update = mocker.patch(
        UPDATE_UUID_PATH,
        return_value={**entity, "monitor_id": "", "node_id": "node-keep"},
    )
    node_mgmt = mocker.patch("apps.rpc.node_mgmt.NodeMgmt")

    result = MonitorLinkService.unbind(INST_UUID, ACTOR_SCOPE)

    assert result == {"status": "ok", "failed_side": None}
    monitor.ingest_from_source.assert_called_once()
    kwargs = monitor.ingest_from_source.call_args.kwargs
    assert kwargs["event_type"] == "lifecycle"
    assert kwargs["raw"]["action"] == "unlink"
    assert kwargs["link_ids"]["cmdb_id"] == INST_UUID
    assert kwargs["link_ids"]["monitor_id"] == "m-linked"
    assert "node_id" not in kwargs["link_ids"]
    update.assert_called_once()
    update_kwargs = update.call_args.kwargs
    assert update_kwargs["update_attr"] == {"monitor_id": ""}
    assert "node_id" not in update_kwargs["update_attr"]
    assert update_kwargs["skip_permission_check"] is True
    node_mgmt.assert_not_called()


def test_unbind_without_monitor_id_is_idempotent(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID, monitor_id=""))
    monitor = _monitor(mocker)
    update = mocker.patch(UPDATE_UUID_PATH)

    result = MonitorLinkService.unbind(INST_UUID, ACTOR_SCOPE)

    assert result == {"status": "ok", "failed_side": None}
    monitor.ingest_from_source.assert_not_called()
    update.assert_not_called()


def test_unbind_monitor_exception_does_not_clear_cmdb(mocker, caplog):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    boom = RuntimeError(secret)
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID, monitor_id="m-linked"))
    monitor = mocker.Mock()
    monitor.ingest_from_source.side_effect = boom
    mocker.patch(MONITOR_PATH, return_value=monitor)
    update = mocker.patch(UPDATE_UUID_PATH)

    with caplog.at_level(logging.ERROR, logger="cmdb"):
        result = MonitorLinkService.unbind(INST_UUID, ACTOR_SCOPE)

    assert result == {"status": "failed", "failed_side": "monitor"}
    update.assert_not_called()
    records = [r for r in caplog.records if r.name == "cmdb" and r.msg == UNBIND_FAILED_TEMPLATE]
    assert len(records) == 1
    record = records[0]
    assert record.args == (INST_UUID, "ingest_unlink", "RuntimeError")
    assert record.exc_info is not None
    assert record.exc_info[2] is boom.__traceback__
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert secret not in record.getMessage()
    assert boom.args == (secret,)


# ---------------------------------------------------------------------------
# service: candidates
# ---------------------------------------------------------------------------


def test_list_candidates_rows_include_name(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID))
    rows = [
        {"id": "m-1", "name": "web-1", "ip": "10.1.1.1", "object_name": "Host", "cmdb_id": None},
    ]
    monitor = _monitor(mocker, list_cmdb_bind_candidates=rows)

    result = MonitorLinkService.list_candidates(INST_UUID, "web", ACTOR_SCOPE)

    assert result["status"] == "ok"
    assert result["items"] == rows
    assert result["items"][0]["name"] == "web-1"
    monitor.list_cmdb_bind_candidates.assert_called_once_with(
        object_name="Host",
        query="web",
        allowed_org_ids=[1],
        limit=50,
    )


def test_list_candidates_skipped_model(mocker):
    mocker.patch(QUERY_PATH, return_value=_entity(INST_UUID, model_id="weblogic"))
    monitor = _monitor(mocker)

    result = MonitorLinkService.list_candidates(INST_UUID, "", ACTOR_SCOPE)

    assert result["status"] == "skipped_model"
    monitor.list_cmdb_bind_candidates.assert_not_called()


# ---------------------------------------------------------------------------
# view
# ---------------------------------------------------------------------------


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.group_tree = []
    u.roles = ["admin"]
    return u


@pytest.fixture(autouse=True)
def _perm(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id="", permission_type=None: {1: {"permission_instances_map": {}, "inst_names": []}},
    )
    monkeypatch.setattr(f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission", lambda **kwargs: True)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_creator_and_organizations", lambda self, r, i: True)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [1])
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_instance_permission", lambda self, r, i, operator=None: True)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.require_instance_permission", lambda self, r, i, operator=None: None)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet._get_allowed_org_ids", staticmethod(lambda request: [1]))
    monkeypatch.setattr(
        f"{VIEWS}.build_cmdb_push_actor_scope",
        lambda request: {"allowed_org_ids": [1], "operator": "test"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": model_id, "is_visible": True},
    )
    monkeypatch.setattr(f"{VIEWS}.ModelManage.search_model_attr", lambda model_id: [])


def _req(method, user, data=None, query=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    if method == "get":
        request = fn("/x/", query or {})
    elif data is None:
        request = fn("/x/")
    else:
        request = fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _call(action_map, request, **kwargs):
    return InstanceViewSet.as_view(action_map)(request, **kwargs)


@pytest.mark.django_db
def test_rebind_without_confirm_is_409(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk, monitor_id="m-old"))

    captured = {}

    def _bind(inst_uuid, monitor_id, actor_scope, *, confirm=False):
        captured["confirm"] = confirm
        captured["monitor_id"] = monitor_id
        return {"status": "confirm_required", "monitor_id": "m-old"}

    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.bind", _bind)

    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "m-new"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    body = _body(response)
    assert body["result"] is False
    assert body["data"]["status"] == "confirm_required"
    assert captured["confirm"] is False
    assert captured["monitor_id"] == "m-new"


@pytest.mark.django_db
def test_bind_occupied_view_is_409_with_occupier_name(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.bind",
        lambda *a, **k: {
            "status": "occupied",
            "occupied_inst_name": "occupied-host",
            "occupied_inst_uuid": OCCUPIED_UUID,
            "occupied_cmdb_id": OCCUPIED_UUID,
        },
    )
    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "m-occ"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    data = _body(response)["data"]
    assert data["occupied_inst_name"] == "occupied-host"
    assert data["occupied_inst_uuid"] == OCCUPIED_UUID


@pytest.mark.django_db
def test_bind_digit_pk_is_400(superuser, monkeypatch):
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.bind", lambda *a, **k: called.append(1))
    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "m-1"}),
        pk="12345",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert called == []


@pytest.mark.django_db
def test_candidates_view_rows_include_name(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    rows = [{"id": "m-1", "name": "alpha", "ip": "10.0.0.1", "object_name": "Host"}]
    captured = {}

    def _list(inst_uuid, query, actor_scope):
        captured["query"] = query
        return {"status": "ok", "items": rows}

    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.list_candidates", _list)
    response = _call(
        {"get": "monitor_bind_candidates"},
        _req("get", superuser, query={"q": "alpha"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["result"] is True
    assert body["data"][0]["name"] == "alpha"
    assert captured["query"] == "alpha"


@pytest.mark.django_db
def test_unbind_view_ok(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk, monitor_id="m-1"))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.unbind",
        lambda inst_uuid, actor_scope: {"status": "ok", "failed_side": None},
    )
    response = _call({"post": "unbind_monitor"}, _req("post", superuser, data={}), pk=INST_UUID)
    assert response.status_code == status.HTTP_200_OK
    assert _body(response)["result"] is True


@pytest.mark.django_db
def test_bind_monitor_not_found_is_404(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.bind",
        lambda *a, **k: {"status": "not_found"},
    )
    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "missing"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_candidates_skipped_model_is_400(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk, model_id="weblogic"))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.list_candidates",
        lambda *a, **k: {"status": "skipped_model"},
    )
    response = _call({"get": "monitor_bind_candidates"}, _req("get", superuser), pk=INST_UUID)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_bind_missing_instance_is_404(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: None)
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.bind", lambda *a, **k: called.append(1))
    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "m-1"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert called == []


@pytest.mark.django_db
def test_bind_no_edit_permission_is_403(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_creator_and_organizations", lambda self, r, i: False)
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [1])
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_instance_permission", lambda self, r, i, operator=None: False)
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.bind", lambda *a, **k: called.append(1))
    response = _call(
        {"post": "bind_monitor"},
        _req("post", superuser, data={"monitor_id": "m-1"}),
        pk=INST_UUID,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert called == []

"""CMDB 批量推送到监控：instance view 接口层。"""

import json
import logging

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.services.monitor_link import BATCH_PUSH_LIMIT
from apps.cmdb.views.instance import InstanceViewSet

VIEWS = "apps.cmdb.views.instance"
BATCH_PUSH_FAILED_TEMPLATE = "event=cmdb_monitor_link_batch_push_failed failed_stage=%s error_type=%s total=%s"


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
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.has_object_permission",
        lambda **kwargs: True,
    )
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


def _req(method, user, data=None, team="1", include_children="0"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _call(action_map, request, **kwargs):
    return InstanceViewSet.as_view(action_map)(request, **kwargs)


def _entity(inst_uuid, model_id="host"):
    return {"inst_uuid": inst_uuid, "model_id": model_id, "inst_name": inst_uuid, "organization": [1]}


def _summary(**overrides):
    payload = {
        "total": 0,
        "ok": 0,
        "already_linked": 0,
        "not_found": 0,
        "conflict": 0,
        "failed": 0,
        "results": [],
    }
    payload.update(overrides)
    return payload


def _post_batch(user, data):
    return _call({"post": "batch_push_to_monitor"}, _req("post", user, data=data))


@pytest.mark.django_db
def test_batch_push_empty_or_missing_is_400(superuser):
    for payload in ({}, {"inst_uuids": []}, {"inst_uuids": "u-1"}, {"inst_uuids": None}):
        response = _post_batch(superuser, payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        body = _body(response)
        assert body["result"] is False


@pytest.mark.django_db
def test_batch_push_over_limit_is_400(superuser, monkeypatch):
    called = []
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.batch_push",
        lambda *a, **k: called.append(1) or _summary(),
    )
    uuids = [f"u-{i}" for i in range(BATCH_PUSH_LIMIT + 1)]
    response = _post_batch(superuser, {"inst_uuids": uuids})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert called == []


@pytest.mark.django_db
def test_batch_push_two_authorized_returns_service_summary(superuser, monkeypatch):
    entities = {"u-1": _entity("u-1"), "u-2": _entity("u-2")}
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda pk: entities.get(pk),
    )
    actor_scope = {"allowed_org_ids": [1], "operator": "alice"}
    monkeypatch.setattr(f"{VIEWS}.build_cmdb_push_actor_scope", lambda request: actor_scope)
    summary = _summary(
        total=2,
        ok=1,
        already_linked=1,
        results=[
            {"inst_uuid": "u-1", "status": "ok", "monitor_id": "m-1"},
            {"inst_uuid": "u-2", "status": "already_linked", "monitor_id": "m-keep"},
        ],
    )
    captured = {}

    def _batch_push(inst_uuids, *, actor_scope):
        captured["inst_uuids"] = list(inst_uuids)
        captured["actor_scope"] = actor_scope
        return summary

    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.batch_push", _batch_push)

    response = _post_batch(superuser, {"inst_uuids": ["u-1", "u-2"]})
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["result"] is True
    assert body["data"] == summary
    assert captured["inst_uuids"] == ["u-1", "u-2"]
    assert captured["actor_scope"] is actor_scope


@pytest.mark.django_db
def test_batch_push_mixed_permission_keeps_200_and_filters_service_input(superuser, monkeypatch):
    entities = {"u-ok": _entity("u-ok"), "u-deny": _entity("u-deny")}
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda pk: entities.get(pk),
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceViewSet.check_creator_and_organizations",
        lambda self, r, instance: instance.get("inst_uuid") == "u-ok",
    )
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.organizations", lambda self, r, i: [1])
    monkeypatch.setattr(f"{VIEWS}.InstanceViewSet.check_instance_permission", lambda self, r, i, operator=None: False)

    captured = {}

    def _batch_push(inst_uuids, *, actor_scope):
        captured["inst_uuids"] = list(inst_uuids)
        return _summary(
            total=1,
            ok=1,
            results=[{"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-1"}],
        )

    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.batch_push", _batch_push)

    response = _post_batch(superuser, {"inst_uuids": ["u-deny", "u-ok"]})
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["result"] is True
    assert captured["inst_uuids"] == ["u-ok"]
    data = body["data"]
    assert data["total"] == 2
    assert data["ok"] == 1
    assert data["failed"] == 1
    assert data["results"] == [
        {"inst_uuid": "u-deny", "status": "failed", "monitor_id": None},
        {"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-1"},
    ]


@pytest.mark.django_db
def test_batch_push_digit_id_is_row_failed_not_batch_400(superuser, monkeypatch):
    queried = []
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_uuid",
        lambda pk: queried.append(pk) or _entity(pk),
    )
    captured = {}

    def _batch_push(inst_uuids, *, actor_scope):
        captured["inst_uuids"] = list(inst_uuids)
        return _summary(
            total=1,
            ok=1,
            results=[{"inst_uuid": "u-ok", "status": "ok", "monitor_id": "m-1"}],
        )

    monkeypatch.setattr(f"{VIEWS}.MonitorLinkService.batch_push", _batch_push)

    response = _post_batch(superuser, {"inst_uuids": ["12345", "u-ok"]})
    assert response.status_code == status.HTTP_200_OK
    assert queried == ["u-ok"]
    assert captured["inst_uuids"] == ["u-ok"]
    data = _body(response)["data"]
    assert data["results"][0] == {"inst_uuid": "12345", "status": "failed", "monitor_id": None}


@pytest.mark.django_db
def test_batch_push_missing_instance_is_row_failed(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: None)
    called = []
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.batch_push",
        lambda *a, **k: called.append(1) or _summary(),
    )
    response = _post_batch(superuser, {"inst_uuids": ["u-missing"]})
    assert response.status_code == status.HTTP_200_OK
    data = _body(response)["data"]
    assert called == []
    assert data["total"] == 1
    assert data["failed"] == 1
    assert data["results"] == [{"inst_uuid": "u-missing", "status": "failed", "monitor_id": None}]


@pytest.mark.django_db
def test_batch_push_value_error_is_400(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.batch_push",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("batch push exceeds limit of 100")),
    )
    response = _post_batch(superuser, {"inst_uuids": ["u-1"]})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_batch_push_unexpected_exception_is_502_and_logs(superuser, monkeypatch, caplog):
    secret = "SECRET-PAYLOAD-DO-NOT-LOG"
    boom = RuntimeError(secret)
    monkeypatch.setattr(f"{VIEWS}.InstanceManage.query_entity_by_uuid", lambda pk: _entity(pk))
    monkeypatch.setattr(
        f"{VIEWS}.MonitorLinkService.batch_push",
        lambda *a, **k: (_ for _ in ()).throw(boom),
    )
    with caplog.at_level(logging.ERROR, logger="cmdb"):
        response = _post_batch(superuser, {"inst_uuids": ["u-1"]})
    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert _body(response)["result"] is False
    records = [r for r in caplog.records if r.name == "cmdb" and r.msg == BATCH_PUSH_FAILED_TEMPLATE]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.args == ("batch_push", "RuntimeError", 1)
    assert record.getMessage() == ("event=cmdb_monitor_link_batch_push_failed failed_stage=batch_push error_type=RuntimeError total=1")
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert str(record.exc_info[1]) == "cmdb monitor link batch push failed"
    assert record.exc_info[2] is boom.__traceback__
    assert boom.args == (secret,)
    formatted = logging.Formatter().format(record)
    assert secret not in record.getMessage()
    assert secret not in formatted
    assert secret not in "".join(str(arg) for arg in record.args)

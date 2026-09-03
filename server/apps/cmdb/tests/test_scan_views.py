import json

import pydantic.root_model  # noqa: F401
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.scan_model import ScanExecution, ScanHit, ScanTask
from apps.cmdb.views.scan import ScanTaskViewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.group_list = [{"id": 1}]
    authenticated_user.roles = ["admin"]
    authenticated_user.domain = "domain.com"
    return authenticated_user


def _req(method, user, data=None, query=None, **cookies):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    path = "/x/"
    if query:
        path = "/x/?" + "&".join(f"{k}={v}" for k, v in query.items())
    request = fn(path) if data is None else fn(path, data=data, format="json")
    for k, v in cookies.items():
        request.COOKIES[k] = v
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _data(response):
    body = _body(response)
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _bypass_permission(monkeypatch):
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr("apps.core.utils.permission_utils.get_permission_rules", lambda *a, **k: {})
    monkeypatch.setattr(
        ScanTaskViewSet,
        "get_queryset_by_permission",
        lambda self, request, queryset, permission_key=None: queryset,
    )
    monkeypatch.setattr(
        ScanTaskViewSet,
        "_validate_org_field_permission",
        lambda self, request, org_values: None,
    )


def _payload(**overrides):
    values = {
        "name": "scan-api",
        "team": [1],
        "access_point": [{"id": "node-1", "name": "proxy"}],
        "ip_ranges": [{"begin": "10.0.1.1", "end": "10.0.1.10"}],
        "families": ["database"],
        "credentials": {
            "database": [{"username": "monitor", "password": "db-secret"}],
        },
        "auto_push_monitor": False,
        "auto_generate_collect": False,
    }
    values.update(overrides)
    return values


def test_create_scan_does_not_create_collect_models(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    before = CollectModels.objects.count()
    request = _req("post", superuser, data=_payload(), current_team="1")
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201
    body = _data(response)
    assert body["name"] == "scan-api"
    assert "db-secret" not in json.dumps(body)
    assert body["credentials"]["database"][0]["password"] == "******"
    assert CollectModels.objects.count() == before
    task = ScanTask.objects.get(pk=body["id"])
    assert task.families == ["database"]
    assert "port" not in task.decrypt_credentials["database"][0]
    assert task.decrypt_credentials["database"][0]["password"] == "db-secret"


def test_delete_scan_does_not_call_monitor_lifecycle(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(
        name="scan-delete",
        team=[1],
        families=["mysql"],
        credentials={"mysql": [{"username": "u", "password": "p"}]},
    )
    called = {"ingest": False}

    def _forbidden(*args, **kwargs):
        called["ingest"] = True
        raise AssertionError("delete scan must not touch monitor ingest")

    monkeypatch.setattr(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService.push_instance",
        _forbidden,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.module_push.CmdbToMonitorPushService.best_effort_notify_on_delete",
        _forbidden,
    )
    request = _req("delete", superuser, current_team="1")
    response = ScanTaskViewSet.as_view({"delete": "destroy"})(request, pk=task.id)
    assert response.status_code == 200
    assert not ScanTask.objects.filter(pk=task.id).exists()
    assert called["ingest"] is False


def test_exec_creates_execution_without_collect_models(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr("django.db.transaction.on_commit", lambda fn: fn())
    trigger = []

    def fake_delay(execution_id):
        trigger.append(execution_id)

    monkeypatch.setattr("apps.cmdb.tasks.celery_tasks.trigger_scan_execution.delay", fake_delay)
    task = ScanTask.objects.create(
        name="scan-exec",
        team=[1],
        families=["mysql"],
        credentials={"mysql": [{"username": "u", "password": "p"}]},
    )
    before = CollectModels.objects.count()
    request = _req("post", superuser, data={}, current_team="1")
    response = ScanTaskViewSet.as_view({"post": "exec_scan"})(request, pk=task.id)
    assert response.status_code == 201
    body = _data(response)
    assert ScanExecution.objects.filter(pk=body["id"], task=task).exists()
    assert trigger == [body["id"]]
    assert CollectModels.objects.count() == before


def test_hits_require_pagination(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(
        name="scan-hits",
        team=[1],
        families=["mysql", "host"],
        credentials={
            "mysql": [{"credential_id": "cred-db", "username": "db", "port": "3306", "password": "x"}],
            "host": [{"credential_id": "cred-ssh", "username": "root", "port": "22", "password": "y"}],
        },
    )
    execution = ScanExecution.objects.create(task=task)
    family_run = execution.family_runs.create(model_id="mysql", driver_type="protocol")
    host_run = execution.family_runs.create(model_id="host", driver_type="job")
    network_run = execution.family_runs.create(model_id="network", driver_type="protocol")
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="mysql",
        host="10.0.1.20",
        port=3306,
        credential_id="cred-db",
        status=ScanHit.STATUS_SUCCESS,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=host_run,
        protocol="host",
        host="10.0.1.21",
        port=22,
        credential_id="cred-ssh",
        status=ScanHit.STATUS_FAILED,
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=network_run,
        protocol="network",
        host="10.0.1.11",
        port=161,
        credential_id="cred-snmp",
        status=ScanHit.STATUS_SUCCESS,
        soid="1.2.3.999",
        cmdb_model_id="",
    )
    ScanHit.objects.create(
        execution=execution,
        family_run=family_run,
        protocol="mysql",
        host="10.0.1.22",
        port=3306,
        credential_id="",
        status=ScanHit.STATUS_FAILED,
        error_code="auth_failed",
    )
    request = _req("get", superuser, query={"page": "1", "page_size": "20"}, current_team="1")
    response = ScanTaskViewSet.as_view({"get": "execution_hits"})(request, eid=str(execution.id))
    assert response.status_code == 200
    body = _data(response)
    assert body["count"] == 3
    by_host = {item["host"]: item for item in body["items"]}
    assert by_host["10.0.1.20"]["credential_label"] == "db@3306"
    assert by_host["10.0.1.20"]["unmatch_reason"] == ""
    assert by_host["10.0.1.11"]["unmatch_reason"] == "unknown_soid"
    assert by_host["10.0.1.22"]["unmatch_reason"] == "credential_failed"


def test_generate_collect_returns_created_summary(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(name="scan-gen-api", team=[1])
    execution = ScanExecution.objects.create(task=task)
    monkeypatch.setattr(
        "apps.cmdb.services.scan_collect_generate.ScanCollectGenerateService.generate",
        lambda execution, hit_ids, operator="", request=None: {"created": 1, "appended": 0, "skipped": 0, "failed": 0, "items": []},
    )
    request = _req("post", superuser, data={"hit_ids": [13, 14]}, current_team="1")
    response = ScanTaskViewSet.as_view({"post": "generate_collect"})(request, eid=str(execution.id))
    assert response.status_code == 200
    body = _data(response)
    assert body["created"] == 1


def test_push_monitor_returns_pushed_summary(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(name="scan-push-api", team=[1])
    execution = ScanExecution.objects.create(task=task)
    monkeypatch.setattr(
        "apps.cmdb.services.scan_push_monitor.ScanPushMonitorService.push",
        lambda execution, hit_ids, request=None, operator="": {
            "pushed": 2,
            "skipped": 0,
            "failed": 0,
            "items": [],
        },
    )
    request = _req("post", superuser, data={"hit_ids": [13, 14]}, current_team="1")
    response = ScanTaskViewSet.as_view({"post": "push_monitor"})(request, eid=str(execution.id))
    assert response.status_code == 200
    body = _data(response)
    assert body["pushed"] == 2


def test_classify_hits_returns_classified_summary(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(name="scan-classify-api", team=[1])
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    monkeypatch.setattr(
        "apps.cmdb.services.scan_classify_service.classify_hits",
        lambda execution, hit_ids, cmdb_model_id: {
            "classified": 1,
            "skipped": 0,
            "failed": 0,
            "items": [],
        },
    )
    request = _req("post", superuser, data={"hit_ids": [21], "cmdb_model_id": "router"}, current_team="1")
    response = ScanTaskViewSet.as_view({"post": "classify_hits"})(request, eid=str(execution.id))
    assert response.status_code == 200
    assert _data(response)["classified"] == 1


def test_rematch_soid_returns_classified_summary(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(name="scan-rematch-api", team=[1])
    execution = ScanExecution.objects.create(task=task, status=ScanExecution.STATUS_COMPLETED)
    captured = {}

    def fake_rematch(execution, soid, hit_ids=None):
        captured["soid"] = soid
        captured["hit_ids"] = hit_ids
        return {"classified": 2, "skipped": 0, "failed": 0, "items": []}

    monkeypatch.setattr("apps.cmdb.services.scan_classify_service.rematch_soid", fake_rematch)
    request = _req("post", superuser, data={"soid": "1.2.3.999", "hit_ids": [31, 32]}, current_team="1")
    response = ScanTaskViewSet.as_view({"post": "rematch_soid"})(request, eid=str(execution.id))
    assert response.status_code == 200
    assert _data(response)["classified"] == 2
    assert captured["soid"] == "1.2.3.999"
    assert captured["hit_ids"] == [31, 32]


def test_create_merges_legacy_sql_families_into_database(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    request = _req(
        "post",
        superuser,
        data=_payload(
            families=["mysql", "postgresql", "network"],
            credentials={
                "mysql": [{"credential_id": "cred-a", "username": "a", "password": "pa", "port": 3306}],
                "postgresql": [{"credential_id": "cred-b", "username": "b", "password": "pb", "port": 5432}],
                "network": [{"version": "v2c", "community": "public"}],
            },
        ),
        current_team="1",
    )
    response = ScanTaskViewSet.as_view({"post": "create"})(request)
    assert response.status_code == 201
    body = _data(response)
    assert body["families"] == ["database", "network"]
    usernames = [item["username"] for item in body["credentials"]["database"]]
    assert usernames == ["a", "b"]
    task = ScanTask.objects.get(pk=body["id"])
    assert task.families == ["database", "network"]
    assert set(task.decrypt_credentials) == {"database", "network"}


def test_retrieve_old_mysql_task_looks_like_database(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    task = ScanTask.objects.create(
        name="scan-legacy-sql",
        team=[1],
        access_point=[{"id": "node-1"}],
        ip_ranges=[{"begin": "10.0.1.1", "end": "10.0.1.2"}],
        families=["mysql"],
        credentials={"mysql": [{"username": "legacy", "password": "secret", "port": 3306}]},
    )
    request = _req("get", superuser, current_team="1")
    response = ScanTaskViewSet.as_view({"get": "retrieve"})(request, pk=task.id)
    assert response.status_code == 200
    body = _data(response)
    assert body["families"] == ["database"]
    assert body["credentials"]["database"][0]["username"] == "legacy"
    assert body["credentials"]["database"][0]["password"] == "******"
    assert "port" not in body["credentials"]["database"][0]

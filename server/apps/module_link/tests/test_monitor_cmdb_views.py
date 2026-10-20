import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.module_link.constants import BATCH_LIMIT
from apps.module_link.views import MonitorCmdbTaskViewSet

VIEWS = "apps.module_link.views"
pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.group_list = [{"id": 1}]
    return authenticated_user


def _req(method, user, data=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn("/x/") if data is None else fn("/x/", data=data, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def test_create_empty_is_400(superuser):
    response = MonitorCmdbTaskViewSet.as_view({"post": "create"})(_req("post", superuser, {}))
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_create_over_limit_is_400(superuser, monkeypatch):
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.create", lambda *a, **k: called.append(1))
    response = MonitorCmdbTaskViewSet.as_view({"post": "create"})(
        _req("post", superuser, {"monitor_ids": [f"m-{i}" for i in range(BATCH_LIMIT + 1)], "object_name": "Host"})
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert called == []


def test_create_returns_serialized_task(superuser, monkeypatch):
    task = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.create", lambda monitor_ids, object_name, request: task)
    monkeypatch.setattr(
        f"{VIEWS}.serialize_monitor_cmdb_task",
        lambda saved: {"id": str(saved.id), "status": "waiting_create", "items": []},
    )
    response = MonitorCmdbTaskViewSet.as_view({"post": "create"})(_req("post", superuser, {"monitor_ids": ["m-1"], "object_name": "Host"}))
    assert response.status_code == status.HTTP_200_OK
    body = _body(response)
    assert body["result"] is True
    assert body["data"]["id"] == str(task.id)


def test_retrieve_missing_is_404(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.get_task", lambda pk, request: None)
    response = MonitorCmdbTaskViewSet.as_view({"get": "retrieve"})(_req("get", superuser), pk=str(uuid4()))
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_requires_monitor_permission(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"cmdb": {"asset_info-Edit"}}
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.create", lambda *a, **k: called.append(1))
    response = MonitorCmdbTaskViewSet.as_view({"post": "create"})(_req("post", authenticated_user, {"monitor_ids": ["m-1"], "object_name": "Host"}))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert called == []


def test_create_missing_empty_is_400(superuser, monkeypatch):
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.get_task", lambda pk, request: SimpleNamespace(id=pk))
    called = []
    monkeypatch.setattr(f"{VIEWS}.MonitorCmdbTaskService.create_missing", lambda *a, **k: called.append(1))
    response = MonitorCmdbTaskViewSet.as_view({"post": "create_missing"})(
        _req("post", superuser, {}),
        pk=str(uuid4()),
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert called == []

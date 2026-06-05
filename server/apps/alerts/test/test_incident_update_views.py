"""事故协作更新视图覆盖测试。

对照 spec/prd/告警中心·事故：负责人/协作者可发布协作更新与回复，仅作者可编辑/删除。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.models import Incident, IncidentUpdate
from apps.alerts.views.incident_update import IncidentUpdateViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture(autouse=True)
def _grant(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"instance": [], "team": ["1"]},
    )


def _request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _make_incident(operator=None):
    return Incident.objects.create(
        incident_id="I1", level="0", title="t", fingerprint="fp", team=[1],
        operator=operator or ["testuser"],
    )


@pytest.mark.django_db
def test_incident_update_list(superuser):
    incident = _make_incident()
    IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="进展1")
    request = _request("get", "/incident/1/updates/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "list"})(request, incident_pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


@pytest.mark.django_db
def test_incident_update_list_with_replies_author_map(superuser):
    from apps.system_mgmt.models.user import User as SysUser

    SysUser.objects.create(username="testuser", display_name="测试用户", domain="domain.com")
    incident = _make_incident()
    parent = IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="父")
    IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="子", parent=parent)
    request = _request("get", "/incident/1/updates/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "list"})(request, incident_pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    # 顶层只返回非回复
    assert len(items) == 1


@pytest.mark.django_db
def test_incident_update_list_incident_not_found(superuser):
    request = _request("get", "/incident/999/updates/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "list"})(request, incident_pk="999")
    _render(response)
    assert response.status_code == 400


@pytest.mark.django_db
def test_incident_update_create(superuser):
    incident = _make_incident(operator=["testuser"])
    data = {"update_type": "progress", "content": "新的进展"}
    request = _request("post", "/incident/1/updates/", superuser, data=data)
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert IncidentUpdate.objects.filter(incident=incident, content="新的进展").exists()


@pytest.mark.django_db
def test_incident_update_create_not_collaborator(superuser):
    # testuser 不在 operator/collaborators 中 → 403
    incident = _make_incident(operator=["someoneelse"])
    data = {"update_type": "progress", "content": "x"}
    request = _request("post", "/incident/1/updates/", superuser, data=data)
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_incident_update_create_reply(superuser):
    incident = _make_incident(operator=["testuser"])
    parent = IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="父更新")
    data = {"update_type": "progress", "content": "回复内容", "parent": parent.id}
    request = _request("post", "/incident/1/updates/", superuser, data=data)
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert IncidentUpdate.objects.filter(parent=parent).exists()


@pytest.mark.django_db
def test_incident_update_partial_update_by_author(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="旧内容")
    request = _request("patch", f"/incident/1/updates/{upd.id}/", superuser, data={"content": "新内容"})
    response = IncidentUpdateViewSet.as_view({"patch": "partial_update"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    upd.refresh_from_db()
    assert upd.content == "新内容"


@pytest.mark.django_db
def test_incident_update_partial_update_non_author_forbidden(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(incident=incident, author="someoneelse", update_type="progress", content="x")
    request = _request("patch", f"/incident/1/updates/{upd.id}/", superuser, data={"content": "y"})
    response = IncidentUpdateViewSet.as_view({"patch": "partial_update"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_incident_update_destroy_by_author(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="progress", content="x")
    request = _request("delete", f"/incident/1/updates/{upd.id}/", superuser)
    response = IncidentUpdateViewSet.as_view({"delete": "destroy"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert not IncidentUpdate.objects.filter(id=upd.id).exists()
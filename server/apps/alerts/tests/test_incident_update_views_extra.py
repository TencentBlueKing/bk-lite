"""事故协作更新视图：关键信息标记 / 诊断聚合 / 回复目标缺失 / 删除越权 补充覆盖。

对照 specs/capabilities/legacy-prd-告警中心-事故.md：仅负责人可标记关键信息；诊断面板按更新类型聚合关键信息；
回复目标不存在返回 400；仅作者可删除更新。
"""

import pydantic.root_model  # noqa

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.constants.constants import IncidentUpdateType
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


# --------------------------------------------------------------------------
# create: 回复目标不存在 -> 400
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_reply_parent_not_found(superuser):
    incident = _make_incident(operator=["testuser"])
    data = {"update_type": "progress", "content": "回复", "parent": 999999}
    request = _request("post", "/incident/1/updates/", superuser, data=data)
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident.id))
    _render(response)
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_incident_not_found(superuser):
    request = _request("post", "/incident/999/updates/", superuser, data={"update_type": "progress", "content": "x"})
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk="999")
    _render(response)
    assert response.status_code == 400


# --------------------------------------------------------------------------
# destroy: 非作者 -> 403
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_destroy_non_author_forbidden(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(incident=incident, author="someoneelse", update_type="progress", content="x")
    request = _request("delete", f"/incident/1/updates/{upd.id}/", superuser)
    response = IncidentUpdateViewSet.as_view({"delete": "destroy"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert IncidentUpdate.objects.filter(id=upd.id).exists()


# --------------------------------------------------------------------------
# toggle_key_info
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_toggle_key_info_marks_then_serializes(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type="observation", content="观察内容", is_key_info=False
    )
    request = _request("post", f"/incident/1/updates/{upd.id}/key_info/", superuser)
    response = IncidentUpdateViewSet.as_view({"post": "toggle_key_info"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    upd.refresh_from_db()
    assert upd.is_key_info is True


@pytest.mark.django_db
def test_toggle_key_info_unmarks(superuser):
    incident = _make_incident(operator=["testuser"])
    upd = IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type="observation", content="x", is_key_info=True
    )
    request = _request("post", f"/incident/1/updates/{upd.id}/key_info/", superuser)
    response = IncidentUpdateViewSet.as_view({"post": "toggle_key_info"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_200_OK
    upd.refresh_from_db()
    assert upd.is_key_info is False


@pytest.mark.django_db
def test_toggle_key_info_non_operator_forbidden(superuser):
    incident = _make_incident(operator=["someoneelse"])
    upd = IncidentUpdate.objects.create(incident=incident, author="testuser", update_type="observation", content="x")
    request = _request("post", f"/incident/1/updates/{upd.id}/key_info/", superuser)
    response = IncidentUpdateViewSet.as_view({"post": "toggle_key_info"})(request, incident_pk=str(incident.id), pk=str(upd.id))
    _render(response)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_toggle_key_info_incident_not_found(superuser):
    request = _request("post", "/incident/999/updates/1/key_info/", superuser)
    response = IncidentUpdateViewSet.as_view({"post": "toggle_key_info"})(request, incident_pk="999", pk="1")
    _render(response)
    assert response.status_code == 400


# --------------------------------------------------------------------------
# diagnosis
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_diagnosis_aggregates_key_updates_by_type(superuser):
    incident = _make_incident(operator=["testuser"])
    IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type=IncidentUpdateType.OBSERVATION,
        content="假设", is_key_info=True,
    )
    IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type=IncidentUpdateType.CONCLUSION,
        content="结论", is_key_info=True,
    )
    request = _request("get", "/incident/1/updates/diagnosis/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "diagnosis"})(request, incident_pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"] if "data" in payload else payload
    assert data["current_hypothesis"]["content"] == "假设"
    assert data["confirmed_facts"]["content"] == "结论"
    # 没有关键的 next_step → None
    assert data["next_actions"] is None


@pytest.mark.django_db
def test_diagnosis_all_none_when_no_key_info(superuser):
    incident = _make_incident(operator=["testuser"])
    IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type=IncidentUpdateType.OBSERVATION,
        content="非关键", is_key_info=False,
    )
    request = _request("get", "/incident/1/updates/diagnosis/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "diagnosis"})(request, incident_pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"] if "data" in payload else payload
    assert data["current_hypothesis"] is None
    assert data["confirmed_facts"] is None
    assert data["next_actions"] is None


@pytest.mark.django_db
def test_diagnosis_incident_not_found(superuser):
    request = _request("get", "/incident/999/updates/diagnosis/", superuser)
    response = IncidentUpdateViewSet.as_view({"get": "diagnosis"})(request, incident_pk="999")
    _render(response)
    assert response.status_code == 400

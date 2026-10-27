"""协作更新的 parent 在编辑时不可改挂。

创建回复仍只能挂到当前事故的顶层更新。已有跨事故记录不在这里改写。
"""

import json

import pydantic.root_model  # noqa: F401
import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.models import Incident, IncidentUpdate
from apps.alerts.serializers.incident_update import IncidentUpdateSerializer
from apps.alerts.views.incident_update import IncidentUpdateViewSet
from apps.base.models import User

TEAM_A_CONTENT = "team-a-isolated-update"
TEAM_B_CONTENT = "team-b-parent-content-9f3a"
REWRITTEN_CONTENT = "should-not-be-written"


@pytest.fixture
def collaborator(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.group_list = [{"id": 1, "name": "Team 1"}]
    authenticated_user.permission = {"alarm": {"Incidents-View", "Incidents-Edit"}}
    authenticated_user.save(update_fields=["is_superuser", "group_list"])
    return authenticated_user


def _request(method, path, user, data=None, team="1", query=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    if method == "get":
        request = fn(path, data=query or {})
    elif data is None:
        request = fn(path)
    else:
        request = fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _updates(payload):
    data = payload.get("data", payload)
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(data, list):
        return data
    return []


def _reply_contents(payload):
    contents = []
    for item in _updates(payload):
        for reply in item.get("replies") or []:
            contents.append(reply.get("content"))
    return contents


def _make_incident(incident_id, team, collaborators=None, operator=None):
    return Incident.objects.create(
        incident_id=incident_id,
        level="0",
        title="t",
        fingerprint=f"fp-{incident_id}",
        team=team,
        operator=operator or [],
        collaborators=collaborators or [],
    )


def _viewer_for_team(team_id, username):
    user = User.objects.create_user(
        username=username,
        password="testpass123",
        domain="domain.com",
        locale="en",
        group_list=[{"id": team_id, "name": f"Team {team_id}"}],
        roles=["admin"],
    )
    user.is_superuser = False
    user.permission = {"alarm": {"Incidents-View"}}
    user.save(update_fields=["is_superuser", "group_list"])
    return user


def _list_replies(user, incident, team):
    request = _request(
        "get",
        f"/incident/{incident.id}/updates/",
        user,
        team=str(team),
        query={"page_size": 100},
    )
    response = IncidentUpdateViewSet.as_view({"get": "list"})(request, incident_pk=str(incident.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    return payload


def _patch(user, incident, update, data):
    request = _request(
        "patch",
        f"/incident/{incident.id}/updates/{update.id}/",
        user,
        data=data,
    )
    response = IncidentUpdateViewSet.as_view({"patch": "partial_update"})(
        request, incident_pk=str(incident.id), pk=str(update.id)
    )
    payload = _render(response)
    return response, payload


@pytest.mark.django_db
def test_patch_cross_incident_parent_is_rejected(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    incident_b = _make_incident("IB", [2], operator=["userb"])
    own = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content=TEAM_A_CONTENT
    )
    parent_b = IncidentUpdate.objects.create(
        incident=incident_b, author="userb", update_type="progress", content=TEAM_B_CONTENT
    )

    response, payload = _patch(collaborator, incident_a, own, {"parent": parent_b.id, "content": REWRITTEN_CONTENT})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    rendered = json.dumps(payload, ensure_ascii=False)
    assert TEAM_B_CONTENT not in rendered
    own.refresh_from_db()
    assert own.parent_id is None
    assert own.content == TEAM_A_CONTENT

    viewer_b = _viewer_for_team(2, "userb")
    listed = _list_replies(viewer_b, incident_b, 2)
    assert TEAM_A_CONTENT not in _reply_contents(listed)
    assert TEAM_A_CONTENT not in json.dumps(listed, ensure_ascii=False)


@pytest.mark.django_db
def test_patch_same_incident_reparent_is_rejected(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    own = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content=TEAM_A_CONTENT
    )
    other = IncidentUpdate.objects.create(
        incident=incident_a, author="someone", update_type="progress", content="other-parent"
    )

    response, _payload = _patch(collaborator, incident_a, own, {"parent": other.id, "content": REWRITTEN_CONTENT})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    own.refresh_from_db()
    assert own.parent_id is None
    assert own.content == TEAM_A_CONTENT
    assert not IncidentUpdate.objects.filter(parent=other, content=TEAM_A_CONTENT).exists()


@pytest.mark.django_db
def test_patch_empty_or_self_parent_is_rejected(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    own = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content=TEAM_A_CONTENT
    )

    for parent_value in (None, "", own.id):
        response, payload = _patch(
            collaborator, incident_a, own, {"parent": parent_value, "content": REWRITTEN_CONTENT}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert TEAM_B_CONTENT not in json.dumps(payload, ensure_ascii=False)
        own.refresh_from_db()
        assert own.parent_id is None
        assert own.content == TEAM_A_CONTENT


@pytest.mark.django_db
def test_patch_content_without_parent_succeeds(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    own = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content=TEAM_A_CONTENT
    )

    response, _payload = _patch(collaborator, incident_a, own, {"content": "updated-content"})

    assert response.status_code == status.HTTP_200_OK
    own.refresh_from_db()
    assert own.content == "updated-content"
    assert own.parent_id is None


@pytest.mark.django_db
def test_patch_same_parent_id_still_updates_content(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    parent = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content="kept-parent"
    )
    reply = IncidentUpdate.objects.create(
        incident=incident_a,
        author="testuser",
        update_type="progress",
        content="reply-body",
        parent=parent,
    )
    request = _request("patch", f"/incident/{incident_a.id}/updates/{reply.id}/", collaborator, data={})
    serializer = IncidentUpdateSerializer(
        reply,
        data={"content": "reply-edited", "parent": parent.id},
        partial=True,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    reply.refresh_from_db()
    assert reply.content == "reply-edited"
    assert reply.parent_id == parent.id


@pytest.mark.django_db
def test_post_same_incident_reply_succeeds(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    parent = IncidentUpdate.objects.create(
        incident=incident_a, author="testuser", update_type="progress", content="kept-parent"
    )
    request = _request(
        "post",
        f"/incident/{incident_a.id}/updates/",
        collaborator,
        data={"update_type": "progress", "content": "legal-reply", "parent": parent.id},
    )
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident_a.id))
    _render(response)

    assert response.status_code == status.HTTP_201_CREATED
    assert IncidentUpdate.objects.filter(parent=parent, content="legal-reply", incident=incident_a).exists()


@pytest.mark.django_db
def test_post_cross_incident_parent_is_rejected(collaborator):
    incident_a = _make_incident("IA", [1], collaborators=["testuser"])
    incident_b = _make_incident("IB", [2], operator=["userb"])
    parent_b = IncidentUpdate.objects.create(
        incident=incident_b, author="userb", update_type="progress", content=TEAM_B_CONTENT
    )
    request = _request(
        "post",
        f"/incident/{incident_a.id}/updates/",
        collaborator,
        data={"update_type": "progress", "content": "illegal-reply", "parent": parent_b.id},
    )
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident_a.id))
    payload = _render(response)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert TEAM_B_CONTENT not in json.dumps(payload, ensure_ascii=False)
    assert not IncidentUpdate.objects.filter(content="illegal-reply").exists()
    assert not IncidentUpdate.objects.filter(parent=parent_b).exists()

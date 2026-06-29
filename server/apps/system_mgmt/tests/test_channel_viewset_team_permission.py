import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.viewset.channel_viewset import ChannelViewSet


pytestmark = pytest.mark.django_db


def _grant(user, permission):
    user.permission = {"system-manager": {permission}}
    user.group_list = [{"id": 1, "name": "team-a"}]
    user.is_superuser = False
    user.locale = "en"
    return user


def _payload(team):
    return {
        "name": "mail",
        "channel_type": ChannelChoices.EMAIL,
        "config": {
            "smtp_server": "smtp.example.com",
            "port": 25,
            "smtp_user": "sender",
            "smtp_pwd": "secret",
            "mail_sender": "sender@example.com",
        },
        "description": "mail channel",
        "team": team,
    }


def test_create_rejects_team_outside_user_scope(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    factory = APIRequestFactory()
    request = factory.post("/system_mgmt/channel/", _payload([2]), format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 403
    assert not Channel.objects.filter(name="mail").exists()


def test_create_rejects_invalid_team_payload(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    factory = APIRequestFactory()
    request = factory.post("/system_mgmt/channel/", _payload([1, "bad-team"]), format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 400
    assert not Channel.objects.filter(name="mail").exists()


def test_update_rejects_moving_channel_to_unauthorized_team(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Edit")
    channel = Channel.objects.create(
        name="mail",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="old",
        team=[1],
    )

    factory = APIRequestFactory()
    request = factory.put(f"/system_mgmt/channel/{channel.id}/", _payload([2]), format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"put": "update"})(request, pk=channel.id)

    assert response.status_code == 403
    channel.refresh_from_db()
    assert channel.team == [1]


def test_update_allows_authorized_team(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Edit")
    channel = Channel.objects.create(
        name="mail",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="old",
        team=[1],
    )

    factory = APIRequestFactory()
    request = factory.put(f"/system_mgmt/channel/{channel.id}/", _payload(["1"]), format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"put": "update"})(request, pk=channel.id)

    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.team == [1]


def test_superuser_can_create_channel_for_any_team(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Add")
    user.is_superuser = True

    factory = APIRequestFactory()
    request = factory.post("/system_mgmt/channel/", _payload([2]), format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"post": "create"})(request)

    assert response.status_code == 201
    assert Channel.objects.get(name="mail").team == [2]


def test_superuser_can_update_existing_channel_with_empty_team(authenticated_user):
    user = _grant(authenticated_user, "channel_list-Edit")
    user.is_superuser = True
    channel = Channel.objects.create(
        name="mail",
        channel_type=ChannelChoices.EMAIL,
        config={},
        description="old",
        team=[],
    )

    factory = APIRequestFactory()
    payload = _payload([])
    payload["description"] = "new"
    request = factory.put(f"/system_mgmt/channel/{channel.id}/", payload, format="json")
    force_authenticate(request, user=user)

    response = ChannelViewSet.as_view({"put": "update"})(request, pk=channel.id)

    assert response.status_code == 200
    channel.refresh_from_db()
    assert channel.team == []
    assert channel.description == "new"

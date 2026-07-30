import pydantic.root_model  # noqa
import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.enum import ChannelChoices
from apps.opspilot.models import Channel
from apps.opspilot.services.channel_init_service import ChannelInitService
from apps.opspilot.viewsets.channel_view import ChannelViewSet

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ACTION_CASES = [
    ("list", "get", {}, {}),
    ("retrieve", "get", {}, {"pk": "placeholder"}),
    ("create", "post", {"name": "new", "channel_type": "web", "enabled": True}, {}),
    (
        "update",
        "put",
        {"name": "updated", "channel_type": "web", "enabled": True},
        {"pk": "placeholder"},
    ),
    ("partial_update", "patch", {"name": "updated"}, {"pk": "placeholder"}),
    ("destroy", "delete", {}, {"pk": "placeholder"}),
]


def _user(*, roles=None, is_superuser=False):
    return User.objects.create_user(
        username=f"channel_user_{User.objects.count()}",
        password="x",
        domain="domain.com",
        locale="en",
        roles=roles or [],
        is_superuser=is_superuser,
    )


def _request(method, data, *, user, api_pass):
    factory = APIRequestFactory()
    request = getattr(factory, method)("/", data=data, format="json")
    request.api_pass = api_pass
    force_authenticate(request, user=user)
    return request


@pytest.mark.parametrize(("action", "method", "data", "kwargs"), ACTION_CASES)
@pytest.mark.parametrize("api_pass", [False, True])
def test_channel_crud_rejects_non_admin(action, method, data, kwargs, api_pass):
    user = _user()
    channel = Channel.objects.create(name="protected", channel_type="web")
    resolved_kwargs = {"pk": channel.pk} if kwargs else {}
    request = _request(method, data, user=user, api_pass=api_pass)

    response = ChannelViewSet.as_view({method: action})(request, **resolved_kwargs)

    assert response.status_code == 403
    assert Channel.objects.filter(pk=channel.pk, name="protected").exists()
    assert Channel.objects.count() == 1


@pytest.mark.parametrize(
    ("roles", "api_pass"),
    [(["admin"], False), (["opspilot--admin"], True)],
)
def test_channel_list_keeps_admin_role_access(roles, api_pass):
    user = _user(roles=roles)
    Channel.objects.create(name="visible", channel_type="web")
    request = _request("get", {}, user=user, api_pass=api_pass)

    response = ChannelViewSet.as_view({"get": "list"})(request)

    assert response.status_code == 200
    assert [item["name"] for item in response.data] == ["visible"]


def test_channel_initialization_keeps_using_orm_for_non_admin_owner():
    owner = _user()

    ChannelInitService(owner=owner).init()

    assert set(Channel.objects.filter(created_by=owner.username).values_list("channel_type", flat=True)) == {
        ChannelChoices.ENTERPRISE_WECHAT,
        ChannelChoices.DING_TALK,
        ChannelChoices.WEB,
        ChannelChoices.WECHAT_OFFICIAL_ACCOUNT,
    }

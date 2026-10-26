import json
from unittest.mock import patch

import pytest
from django.test import RequestFactory

from apps.core.views import index_view
from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    User,
)
from apps.system_mgmt.models.system_settings import SystemSettings

pytestmark = pytest.mark.django_db

BK_TOKEN = "bk-token-sentinel-SECRET"


def _json(resp):
    return json.loads(resp.content)


def _request(cookies=None):
    request = RequestFactory().get("/api/v1/core/api/get_bk_settings/")
    if cookies:
        request.COOKIES.update(cookies)
    return request


def _create_ready_binding(*, order=1, name="BlueKing"):
    instance = IntegrationInstance.objects.create(
        name=name,
        provider_key="blueking",
        config={
            "bk_url": "https://bk.example.com",
            "app_id": "bk-app",
            "app_token": "app-token-sentinel-SECRET",
            "bk_username": "bk-sync-user",
        },
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name=f"{name} Binding",
        integration_instance=instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        order=order,
    )
    return instance, binding


def test_get_bk_settings_not_ready_returns_branding_and_does_not_call_blueking():
    SystemSettings.objects.update_or_create(key="portal_name", defaults={"value": "Brand"})

    with (
        patch("apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get") as bk_get,
        patch("apps.system_mgmt.utils.bk_user_utils.get_bk_user_info") as verify,
        patch.object(User.objects, "get_or_create") as get_or_create,
    ):
        response = index_view.get_bk_settings(_request(cookies={"bk_token": BK_TOKEN}))

    data = _json(response)
    assert data["result"] is True
    assert data["data"]["bk_login_open"] is False
    assert data["data"]["portal_name"] == "Brand"
    assert "bklite_token" not in response.cookies
    bk_get.assert_not_called()
    verify.assert_not_called()
    get_or_create.assert_not_called()


def test_get_bk_settings_ready_without_cookie_does_not_write_token():
    SystemSettings.objects.update_or_create(key="portal_name", defaults={"value": "Brand"})
    _create_ready_binding()

    with (
        patch("apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get") as bk_get,
        patch.object(User.objects, "get_or_create") as get_or_create,
    ):
        response = index_view.get_bk_settings(_request())

    data = _json(response)
    assert data["result"] is True
    assert data["data"]["bk_login_open"] is True
    assert data["data"]["user"] == {}
    assert data["data"]["portal_name"] == "Brand"
    assert "bklite_token" not in response.cookies
    bk_get.assert_not_called()
    get_or_create.assert_not_called()


def test_get_bk_settings_ready_without_local_user_does_not_write_token():
    _create_ready_binding()

    with (
        patch(
            "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        ) as bk_get,
        patch.object(User.objects, "get_or_create") as get_or_create,
    ):
        bk_get.return_value.status_code = 200
        bk_get.return_value.json.return_value = {"result": True, "data": {"bk_username": "ghost"}}
        response = index_view.get_bk_settings(_request(cookies={"bk_token": BK_TOKEN}))

    data = _json(response)
    assert data["result"] is True
    assert data["data"]["bk_login_open"] is True
    assert data["data"]["user"] == {}
    assert "bklite_token" not in response.cookies
    get_or_create.assert_not_called()
    bk_get.assert_called()


def test_get_bk_settings_match_success_returns_user_token_and_sets_cookie():
    _create_ready_binding()
    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        domain="domain.com",
        password="hashed",
    )

    with (
        patch("apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get") as bk_get,
        patch.object(User.objects, "get_or_create") as get_or_create,
    ):
        bk_get.return_value.status_code = 200
        bk_get.return_value.json.return_value = {"result": True, "data": {"bk_username": "alice"}}
        response = index_view.get_bk_settings(_request(cookies={"bk_token": BK_TOKEN}))

    data = _json(response)
    assert data["result"] is True
    assert data["data"]["bk_login_open"] is True
    assert data["data"]["user"]["username"] == "alice"
    assert data["data"]["user"]["token"]
    assert response.cookies["bklite_token"].value == data["data"]["user"]["token"]
    get_or_create.assert_not_called()


def test_get_bk_settings_uses_first_ready_binding_by_order_and_id():
    _create_ready_binding(order=20, name="Second")
    _, first = _create_ready_binding(order=10, name="First")
    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        domain="domain.com",
        password="hashed",
    )

    with patch(
        "apps.core.views.index_view.execute_login_with_binding",
        return_value={"result": True, "data": {"token": "login-token", "username": "alice"}},
    ) as login:
        response = index_view.get_bk_settings(_request(cookies={"bk_token": BK_TOKEN}))

    login.assert_called_once_with(first.id, bk_token=BK_TOKEN)
    data = _json(response)
    assert data["data"]["user"]["token"] == "login-token"
    assert response.cookies["bklite_token"].value == "login-token"

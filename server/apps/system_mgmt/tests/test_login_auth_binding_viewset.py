from unittest.mock import patch

import pytest

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.fixture
def ready_login_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-login",
        provider_key="feishu",
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def login_binding(ready_login_instance):
    return LoginAuthBinding.objects.create(
        name="feishu-binding",
        integration_instance=ready_login_instance,
        enabled=True,
        external_field="user_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )


@pytest.fixture
def builtin_login_binding(db):
    instance = IntegrationInstance.objects.create(
        name="builtin-login",
        provider_key="bk_lite_builtin",
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
        config={},
    )
    return LoginAuthBinding.objects.create(
        name="builtin-binding",
        integration_instance=instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )


@pytest.mark.django_db
def test_list_returns_bindings(api_client, authenticated_user, login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.get("/api/v1/system_mgmt/login_auth_binding/")

    assert response.status_code == 200
    payload = response.data if isinstance(response.data, list) else response.data.get("results", response.data["items"])
    assert payload[0]["id"] == login_binding.id


@pytest.mark.django_db
def test_create_logs_operation(api_client, authenticated_user, ready_login_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.login_auth_binding_viewset.log_operation") as mock_log:
        response = api_client.post(
            "/api/v1/system_mgmt/login_auth_binding/",
            {
                "name": "created-binding",
                "integration_instance": ready_login_instance.id,
                "enabled": True,
                "external_field": "user_id",
                "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
                "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.DENY,
                "default_group_name": "",
            },
            format="json",
        )

    assert response.status_code == 201
    assert LoginAuthBinding.objects.filter(name="created-binding").exists() is True
    mock_log.assert_called_once()


@pytest.mark.django_db
def test_update_logs_operation(api_client, authenticated_user, login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.login_auth_binding_viewset.log_operation") as mock_log:
        response = api_client.put(
            f"/api/v1/system_mgmt/login_auth_binding/{login_binding.id}/",
            {
                "name": "updated-binding",
                "integration_instance": login_binding.integration_instance_id,
                "enabled": True,
                "external_field": login_binding.external_field,
                "platform_field": login_binding.platform_field,
                "unmatched_user_action": login_binding.unmatched_user_action,
                "default_group_name": login_binding.default_group_name,
            },
            format="json",
        )

    assert response.status_code == 200
    login_binding.refresh_from_db()
    assert login_binding.name == "updated-binding"
    mock_log.assert_called_once()


@pytest.mark.django_db
def test_destroy_rejects_builtin_binding(api_client, authenticated_user, builtin_login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.delete(f"/api/v1/system_mgmt/login_auth_binding/{builtin_login_binding.id}/")

    assert response.status_code == 403
    assert response.json()["message"] == "Built-in login auth binding cannot be deleted"
    assert LoginAuthBinding.objects.filter(id=builtin_login_binding.id).exists() is True


@pytest.mark.django_db
def test_login_url_requires_redirect_uri(api_client, authenticated_user, login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.post(
        f"/api/v1/system_mgmt/login_auth_binding/{login_binding.id}/login_url/",
        {},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["message"] == "redirect_uri is required"


@pytest.mark.django_db
def test_login_url_returns_success_payload(api_client, authenticated_user, login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    runtime_result = CapabilityExecutionResult.success_result("ok", payload={"authorize_url": "https://example.com"})

    with patch("apps.system_mgmt.viewset.login_auth_binding_viewset.build_login_auth_redirect", return_value=runtime_result) as mock_build:
        response = api_client.post(
            f"/api/v1/system_mgmt/login_auth_binding/{login_binding.id}/login_url/",
            {"redirect_uri": "https://console.example.com/callback", "state": "signed"},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["result"] is True
    assert response.data["data"]["payload"]["authorize_url"] == "https://example.com"
    mock_build.assert_called_once_with(
        login_binding,
        redirect_uri="https://console.example.com/callback",
        state="signed",
    )


@pytest.mark.django_db
def test_login_url_returns_failure_payload(api_client, authenticated_user, login_binding):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    runtime_result = CapabilityExecutionResult.failed_result("bad config", code="provider.invalid_config")

    with patch("apps.system_mgmt.viewset.login_auth_binding_viewset.build_login_auth_redirect", return_value=runtime_result):
        response = api_client.post(
            f"/api/v1/system_mgmt/login_auth_binding/{login_binding.id}/login_url/",
            {"redirect_uri": "https://console.example.com/callback"},
            format="json",
        )

    assert response.status_code == 400
    assert response.data["result"] is False
    assert response.data["message"] == "bad config"

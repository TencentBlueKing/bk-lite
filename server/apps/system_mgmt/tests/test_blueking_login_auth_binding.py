import logging
from unittest.mock import patch

import pytest
from rest_framework.exceptions import ValidationError

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
)
from apps.system_mgmt.nats.login_auth_bindings import get_login_auth_bindings
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.serializers.login_auth_binding_serializer import LoginAuthBindingSerializer
from apps.system_mgmt.services.login_auth_binding_service import get_active_login_auth_bindings, login_with_binding


@pytest.fixture
def blueking_instance(db):
    return IntegrationInstance.objects.create(
        name="BlueKing Login",
        provider_key="blueking",
        config={"bk_url": "https://bk.example.com", "app_id": "bk-app", "app_token": "secret", "bk_username": "bk-sync-user"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )


def _blueking_binding_payload(instance, **overrides):
    payload = {
        "name": "BlueKing Binding",
        "integration_instance": instance.id,
        "enabled": True,
        "external_field": "username",
        "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
        "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.DENY,
        "default_group_name": "",
    }
    payload.update(overrides)
    return payload


def test_blueking_login_auth_binding_accepts_unmatched_user_action_create(blueking_instance):
    serializer = LoginAuthBindingSerializer(
        data=_blueking_binding_payload(
            blueking_instance,
            unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
            default_group_name="",
        )
    )

    assert serializer.is_valid(), serializer.errors


def test_blueking_login_auth_binding_rejects_non_username_external_field(blueking_instance):
    serializer = LoginAuthBindingSerializer(data=_blueking_binding_payload(blueking_instance, external_field="email"))

    with pytest.raises(ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)

    assert "external_field" in excinfo.value.detail


def test_blueking_login_auth_binding_rejects_non_username_platform_field(blueking_instance):
    serializer = LoginAuthBindingSerializer(
        data=_blueking_binding_payload(
            blueking_instance,
            platform_field=LoginAuthBindingPlatformFieldChoices.EMAIL,
        )
    )

    with pytest.raises(ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)

    assert "platform_field" in excinfo.value.detail


def test_blueking_login_auth_binding_accepts_locked_username_deny(blueking_instance):
    serializer = LoginAuthBindingSerializer(data=_blueking_binding_payload(blueking_instance))

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_public_login_auth_bindings_exclude_blueking(blueking_instance):
    LoginAuthBinding.objects.create(
        name="BlueKing Binding",
        integration_instance=blueking_instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        order=1,
    )
    feishu_instance = IntegrationInstance.objects.create(
        name="Feishu Login",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    feishu_binding = LoginAuthBinding.objects.create(
        name="Feishu Binding",
        integration_instance=feishu_instance,
        enabled=True,
        external_field="user_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        order=2,
    )

    public = get_login_auth_bindings()
    active = get_active_login_auth_bindings()

    assert public["result"] is True
    assert [item["id"] for item in public["data"]] == [feishu_binding.id]
    assert [item["provider_key"] for item in public["data"]] == ["feishu"]
    assert [binding.id for binding in active] == [feishu_binding.id]
    assert LoginAuthBinding.objects.filter(integration_instance=blueking_instance).count() == 1


@pytest.mark.django_db
def test_login_with_binding_passes_bk_token_to_authenticate(blueking_instance):
    binding = LoginAuthBinding.objects.create(
        name="BlueKing Binding",
        integration_instance=blueking_instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    runtime_result = CapabilityExecutionResult.failed_result("auth failed", code="provider.auth_failed")

    with patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ) as execute:
        result = login_with_binding(binding.id, bk_token="bk-token-sentinel-SECRET")

    assert result["result"] is False
    assert execute.call_args.kwargs["bk_token"] == "bk-token-sentinel-SECRET"
    assert execute.call_args.kwargs["auth_code"] == ""
    assert execute.call_args.kwargs["username"] == ""
    assert execute.call_args.kwargs["password"] == ""


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["provider.auth_failed", "provider.invalid_config", "provider.timeout", "provider.request_failed"])
def test_login_with_binding_skips_error_log_for_blueking_provider_failures(blueking_instance, caplog, code):
    binding = LoginAuthBinding.objects.create(
        name="BlueKing Binding",
        integration_instance=blueking_instance,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    runtime_result = CapabilityExecutionResult.failed_result("auth failed", code=code)

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ):
        result = login_with_binding(binding.id, bk_token="bk-token-sentinel-SECRET")

    assert result["result"] is False
    assert result["message"] == "auth failed"
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "bk-token-sentinel-SECRET" not in caplog.text


@pytest.mark.django_db
def test_login_with_binding_still_error_logs_other_provider_auth_failure(db, caplog):
    instance = IntegrationInstance.objects.create(
        name="Feishu Login",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="Feishu Binding",
        integration_instance=instance,
        enabled=True,
        external_field="user_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    runtime_result = CapabilityExecutionResult.failed_result("auth failed", code="provider.auth_failed")

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ):
        result = login_with_binding(binding.id, auth_code="feishu-code-sentinel")

    assert result["result"] is False
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "feishu-code-sentinel" not in caplog.text

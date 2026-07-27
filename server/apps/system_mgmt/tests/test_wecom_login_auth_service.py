import pytest
from rest_framework.exceptions import ValidationError

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
)
from apps.system_mgmt.serializers.login_auth_binding_serializer import LoginAuthBindingSerializer


@pytest.fixture
def wecom_instance(db):
    return IntegrationInstance.objects.create(
        name="WeCom Login",
        provider_key="wecom",
        config={"corp_id": "ww", "corp_secret": "secret", "agent_id": "100"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )


@pytest.fixture
def wechat_instance(db):
    return IntegrationInstance.objects.create(
        name="WeChat Login",
        provider_key="wechat",
        config={"app_id": "wx", "app_secret": "secret"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )


def _wecom_binding_payload(instance):
    return {
        "name": "WeCom Binding",
        "integration_instance": instance.id,
        "enabled": True,
        "external_field": "userid",
        "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
        "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
        "default_group_name": "WeComGuests",
    }


def test_wecom_login_auth_binding_rejects_unmatched_user_action_create(wecom_instance):
    serializer = LoginAuthBindingSerializer(data=_wecom_binding_payload(wecom_instance))

    with pytest.raises(ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)

    assert "unmatched_user_action" in excinfo.value.detail
    assert "deny" in str(excinfo.value.detail["unmatched_user_action"]).lower()


def test_wecom_login_auth_binding_accepts_unmatched_user_action_deny(wecom_instance):
    payload = _wecom_binding_payload(wecom_instance)
    payload["unmatched_user_action"] = LoginAuthBindingUnmatchedActionChoices.DENY

    serializer = LoginAuthBindingSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors


def test_wechat_login_auth_binding_still_allows_create(wechat_instance):
    serializer = LoginAuthBindingSerializer(data=_wecom_binding_payload(wechat_instance))

    assert serializer.is_valid(), serializer.errors


def test_wecom_login_auth_binding_rejects_external_field_other_than_userid(wecom_instance):
    payload = _wecom_binding_payload(wecom_instance)
    payload["external_field"] = "email"

    serializer = LoginAuthBindingSerializer(data=payload)

    with pytest.raises(ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)

    assert "external_field" in excinfo.value.detail


def test_wecom_login_auth_binding_accepts_external_field_userid(wecom_instance):
    payload = _wecom_binding_payload(wecom_instance)
    payload["unmatched_user_action"] = LoginAuthBindingUnmatchedActionChoices.DENY

    serializer = LoginAuthBindingSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors


def test_wecom_login_auth_binding_update_from_create_to_deny_is_rejected(wecom_instance):
    binding = LoginAuthBinding.objects.create(
        name="Existing WeCom Binding",
        integration_instance=wecom_instance,
        enabled=True,
        external_field="userid",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="WeComGuests",
    )
    serializer = LoginAuthBindingSerializer(
        binding,
        data={
            "name": binding.name,
            "integration_instance": binding.integration_instance_id,
            "enabled": True,
            "external_field": "userid",
            "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
            "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
            "default_group_name": "WeComGuests",
        },
        partial=True,
    )

    with pytest.raises(ValidationError) as excinfo:
        serializer.is_valid(raise_exception=True)

    assert "unmatched_user_action" in excinfo.value.detail

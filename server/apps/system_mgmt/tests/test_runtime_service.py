from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
)
from apps.system_mgmt.providers.adapters.feishu import FeishuLoginAuthAdapter
from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult, RuntimeApplicationService
from apps.system_mgmt.services.login_auth_binding_service import (
    get_active_login_auth_bindings,
    serialize_public_login_auth_binding,
)


def create_builtin_platform_login_auth():
    instance = IntegrationInstance.objects.create(
        name="BK-Lite 账号体系（平台内建）",
        provider_key="bk_lite_builtin",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
        description="系统内建平台账号体系实例",
    )
    binding = LoginAuthBinding.objects.create(
        name="平台账号密码登录",
        integration_instance=instance,
        description="系统内建平台账号密码登录方式",
        order=0,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )
    return instance, binding


class FakeProviderRegistry:
    def __init__(self, manifest):
        self.manifest = manifest

    def get(self, provider_key):
        if provider_key == self.manifest.key:
            return self.manifest
        return None


class FakeAdapterRegistry:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, adapter_key):
        return self.mapping.get(adapter_key)


class UserSyncAdapter:
    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.success_result("user sync ok")


class LoginAuthAdapter:
    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.success_result("login auth ok")


class DemoUserSyncAdapter(BaseUserSyncAdapter):
    pass


def test_runtime_application_service_can_test_single_capability():
    manifest = SimpleNamespace(
        key="demo",
        capabilities=[
            SimpleNamespace(key="user_sync", adapter_key="demo.user_sync"),
            SimpleNamespace(key="login_auth", adapter_key="demo.login_auth"),
        ],
        get_capability=lambda capability_key: next(
            capability for capability in [
                SimpleNamespace(key="user_sync", adapter_key="demo.user_sync"),
                SimpleNamespace(key="login_auth", adapter_key="demo.login_auth"),
            ]
            if capability.key == capability_key
        ),
    )
    instance = SimpleNamespace(provider_key="demo", get_runtime_config=lambda: {"app_id": "cli_xxx"})

    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry(
        {
            "demo.user_sync": UserSyncAdapter,
            "demo.login_auth": LoginAuthAdapter,
        }
    )

    result = service.test_connection(instance, capability_key="user_sync")

    assert result.success is True
    assert result.payload["capability_status"] == {"user_sync": "ready"}


def test_runtime_application_service_logs_failed_capability_details(caplog):
    class FailingAdapter:
        @classmethod
        def test_connection(cls, config, provider_key, capability_key, **kwargs):
            return CapabilityExecutionResult.failed_result(
                "Config field app_secret is missing",
                code="provider.invalid_config",
                field="app_secret",
            )

    manifest = SimpleNamespace(
        key="feishu",
        capabilities=[SimpleNamespace(key="login_auth", adapter_key="feishu.login_auth")],
        get_capability=lambda capability_key: SimpleNamespace(key="login_auth", adapter_key="feishu.login_auth"),
    )
    instance = SimpleNamespace(provider_key="feishu", get_runtime_config=lambda: {})

    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry({"feishu.login_auth": FailingAdapter})

    with caplog.at_level("WARNING"):
        result = service.test_connection(instance)

    assert result.success is False
    assert result.payload["capability_status"] == {"login_auth": "verification_failed"}
    assert "Integration instance test connection failed for capability 'login_auth'" in caplog.text
    assert "provider.invalid_config" in caplog.text
    assert "app_secret" in caplog.text
    assert "request_id=" in caplog.text


def test_runtime_application_service_can_execute_list_departments():
    manifest = SimpleNamespace(
        key="demo",
        capabilities=[SimpleNamespace(key="user_sync", adapter_key="demo.user_sync")],
        get_capability=lambda capability_key: SimpleNamespace(key="user_sync", adapter_key="demo.user_sync"),
    )
    instance = SimpleNamespace(provider_key="demo", get_runtime_config=lambda: {"app_id": "cli_xxx"})

    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry({"demo.user_sync": DemoUserSyncAdapter})

    result = service.execute(
        provider_key="demo",
        capability_key="user_sync",
        operation="list_departments",
        config=instance.get_runtime_config(),
        source=SimpleNamespace(business_config={"department_id_type": "department_id"}),
    )

    assert result.success is True
    assert result.payload["all_department_id"] == "0"
    assert result.payload["items"][0]["id"] == "__all__"


def test_feishu_build_login_url_prints_redirect_uri_and_authorize_url():
    config = {
        "app_id": "cli_test_app",
        "login_auth_authorize_url": "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
    }
    redirect_uri = "http://10.10.40.91:8011/api/v1/core/api/login_auth/callback/"

    with patch("builtins.print") as mock_print:
        result = FeishuLoginAuthAdapter.build_login_url(
            config=config,
            provider_key="feishu",
            capability_key="login_auth",
            redirect_uri=redirect_uri,
            state="state-1",
        )

    assert result.success is True
    mock_print.assert_called_once()
    printed_message = mock_print.call_args.args[0]
    assert "redirect_uri=" in printed_message
    assert redirect_uri in printed_message
    assert "authorize_url=" in printed_message


@pytest.mark.django_db
def test_get_active_login_auth_bindings_includes_builtin_binding():
    builtin_instance, builtin_binding = create_builtin_platform_login_auth()
    IntegrationInstance.objects.create(
        name="Not Ready",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": "pending"},
        enabled=True,
    )

    bindings = get_active_login_auth_bindings()

    assert [binding.id for binding in bindings] == [builtin_binding.id]
    assert bindings[0].integration_instance_id == builtin_instance.id


@pytest.mark.django_db
def test_serialize_public_login_auth_binding_includes_builtin_provider_key():
    instance, binding = create_builtin_platform_login_auth()

    payload = serialize_public_login_auth_binding(binding)

    assert payload["id"] == binding.id
    assert payload["provider_key"] == "bk_lite_builtin"
    assert payload["integration_instance_id"] == instance.id
    assert payload["integration_instance_name"] == instance.name

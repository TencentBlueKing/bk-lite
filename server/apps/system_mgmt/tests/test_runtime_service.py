from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from urllib.parse import parse_qs, urlparse

import pytest

from apps.system_mgmt.models import (
    Group,
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    User,
)
from apps.system_mgmt.providers.adapters.feishu import FeishuLoginAuthAdapter
from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult, RuntimeApplicationService
from apps.system_mgmt.services.login_auth_binding_service import (
    build_login_auth_redirect,
    get_active_login_auth_bindings,
    login_with_binding,
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


class ADLoginAdapter:
    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.success_result("ad login ok")

    @classmethod
    def authenticate(cls, config, provider_key, capability_key, **kwargs):
        username = kwargs.get("username")
        password = kwargs.get("password")
        if username == "alice" and password == "secret":
            return CapabilityExecutionResult.success_result(
                "ad auth ok",
                payload={
                    "external_user": {
                        "sAMAccountName": "alice",
                        "displayName": "Alice",
                        "mail": "alice@example.com",
                        "telephoneNumber": "13800000000",
                        "distinguishedName": "CN=Alice,OU=Users,DC=corp,DC=example,DC=com",
                    }
                },
            )
        return CapabilityExecutionResult.failed_result("bad credentials", code="provider.auth_failed")


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
    assert "Integration instance test connection failed" in caplog.text
    assert "login_auth" in caplog.text
    assert "provider.invalid_config" in caplog.text
    assert "app_secret" in caplog.text
    assert "request_id" in caplog.text


def test_runtime_application_service_aggregates_capability_failures_into_one_log(caplog):
    class FailingAdapter:
        @classmethod
        def test_connection(cls, config, provider_key, capability_key, **kwargs):
            return CapabilityExecutionResult.failed_result(
                f"{capability_key} failed with app_secret=hidden",
                code="provider.auth_failed",
                external_code="401",
                external_request_id=f"external-{capability_key}",
            )

    capabilities = [
        SimpleNamespace(key="login_auth", adapter_key="demo.login_auth"),
        SimpleNamespace(key="user_sync", adapter_key="demo.user_sync"),
    ]
    manifest = SimpleNamespace(
        key="demo",
        capabilities=capabilities,
        get_capability=lambda capability_key: next(
            item for item in capabilities if item.key == capability_key
        ),
    )
    instance = SimpleNamespace(
        id=7,
        name="Demo",
        provider_key="demo",
        get_runtime_config=lambda: {},
    )
    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry(
        {
            "demo.login_auth": FailingAdapter,
            "demo.user_sync": FailingAdapter,
        }
    )

    with caplog.at_level("WARNING"):
        result = service.test_connection(instance)

    failure_logs = [
        record.message
        for record in caplog.records
        if "Integration instance test connection failed" in record.message
    ]
    assert result.success is False
    assert len(failure_logs) == 1
    assert "login_auth" in failure_logs[0]
    assert "user_sync" in failure_logs[0]
    assert "external-login_auth" in failure_logs[0]
    assert "external-user_sync" in failure_logs[0]
    assert "app_secret=hidden" not in failure_logs[0]
    assert result.payload["capability_results"]["login_auth"]["summary"] == (
        "login_auth failed with app_secret=hidden"
    )
    assert result.payload["capability_results"]["user_sync"]["errors"][0]["message"] == (
        "user_sync failed with app_secret=hidden"
    )


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


def test_runtime_application_service_can_execute_ad_authenticate_with_username_password():
    manifest = SimpleNamespace(
        key="ad",
        capabilities=[SimpleNamespace(key="login_auth", adapter_key="ad.login_auth")],
        get_capability=lambda capability_key: SimpleNamespace(key="login_auth", adapter_key="ad.login_auth"),
    )
    instance = SimpleNamespace(provider_key="ad", get_runtime_config=lambda: {"connection_url": "ldap://ad.example.com"})

    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry({"ad.login_auth": ADLoginAdapter})

    result = service.execute(
        provider_key="ad",
        capability_key="login_auth",
        operation="authenticate",
        config=instance.get_runtime_config(),
        username="alice",
        password="secret",
    )

    assert result.success is True
    assert result.payload["external_user"]["sAMAccountName"] == "alice"


def test_runtime_application_service_ad_authenticate_failure_bubbles_up():
    manifest = SimpleNamespace(
        key="ad",
        capabilities=[SimpleNamespace(key="login_auth", adapter_key="ad.login_auth")],
        get_capability=lambda capability_key: SimpleNamespace(key="login_auth", adapter_key="ad.login_auth"),
    )
    instance = SimpleNamespace(provider_key="ad", get_runtime_config=lambda: {"connection_url": "ldap://ad.example.com"})

    service = RuntimeApplicationService()
    service.provider_registry = FakeProviderRegistry(manifest)
    service.adapter_registry = FakeAdapterRegistry({"ad.login_auth": ADLoginAdapter})

    result = service.execute(
        provider_key="ad",
        capability_key="login_auth",
        operation="authenticate",
        config=instance.get_runtime_config(),
        username="alice",
        password="wrong",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.auth_failed"


def test_feishu_build_login_url_returns_authorize_url_payload():
    config = {
        "app_id": "cli_test_app",
        "login_auth_authorize_url": "https://accounts.feishu.cn/open-apis/authen/v1/authorize",
    }
    redirect_uri = "http://10.10.40.91:8011/api/v1/core/api/login_auth/callback/"

    result = FeishuLoginAuthAdapter.build_login_url(
        config=config,
        provider_key="feishu",
        capability_key="login_auth",
        redirect_uri=redirect_uri,
        state="state-1",
    )

    assert result.success is True
    assert "authorize_url" in result.payload
    parsed = urlparse(result.payload["authorize_url"])
    query = parse_qs(parsed.query)
    assert query["redirect_uri"] == [redirect_uri]
    assert query["state"] == ["state-1"]


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


@pytest.mark.django_db
def test_build_login_auth_redirect_delegates_to_runtime_service():
    instance = IntegrationInstance.objects.create(
        name="Feishu Login",
        provider_key="feishu",
        config={"app_id": "cli_xxx"},
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
    runtime_result = CapabilityExecutionResult.success_result("ok", payload={"authorize_url": "https://example.com"})

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result) as mock_execute:
        result = build_login_auth_redirect(binding, redirect_uri="https://console.example.com/callback", state="signed")

    assert result.success is True
    assert result.payload["authorize_url"] == "https://example.com"
    assert mock_execute.call_args.kwargs["binding"] == binding
    assert mock_execute.call_args.kwargs["redirect_uri"] == "https://console.example.com/callback"
    assert mock_execute.call_args.kwargs["state"] == "signed"


@pytest.mark.django_db
def test_login_with_binding_returns_not_found_when_binding_missing():
    result = login_with_binding(999999, "auth-code")

    assert result["result"] is False
    assert result["message"] == "Login auth binding not found"


@pytest.mark.django_db
def test_login_with_binding_rejects_binding_that_is_not_ready():
    instance = IntegrationInstance.objects.create(
        name="Feishu Login",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.PENDING_VERIFICATION},
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

    result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is False
    assert result["message"] == "Login auth binding is not ready"


@pytest.mark.django_db
def test_login_with_binding_returns_provider_failure_payload():
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

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is False
    assert result["message"] == "auth failed"
    assert result["data"]["success"] is False


@pytest.mark.django_db
def test_login_with_binding_returns_adapter_supplied_login_result():
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
    runtime_result = CapabilityExecutionResult.success_result("ok", payload={"login_result": {"token": "abc"}})

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result):
        result = login_with_binding(binding.id, "auth-code")

    assert result == {"result": True, "data": {"token": "abc"}}


@pytest.mark.django_db
def test_login_with_binding_returns_error_when_no_matching_user_found():
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
    runtime_result = CapabilityExecutionResult.success_result("ok", payload={"external_user": {"user_id": "ghost"}})

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is False
    assert result["message"] == "No matching platform user found"


@pytest.mark.django_db
def test_login_with_binding_creates_user_when_unmatched_action_is_create():
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
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsGuests",
    )
    runtime_result = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"user_id": "new-user", "name": "New User", "email": "new@example.com", "mobile": "13800000000"}},
    )

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result), patch(
        "apps.system_mgmt.nats_api.get_user_login_token",
        return_value={"result": True, "data": {"token": "login-token", "username": "new-user"}},
    ):
        result = login_with_binding(binding.id, "auth-code")

    created_user = User.objects.get(username="new-user")
    default_group = Group.objects.get(name="OpsGuests", parent_id=0)
    assert created_user.group_list == [default_group.id]
    assert result["result"] is True
    assert result["data"]["domain"] == "domain.com"


@pytest.mark.django_db
def test_login_with_binding_does_not_modify_existing_user_profile():
    """登录认证不修改已有用户资料,只刷 last_login(由外层 login_with_binding 处理)。

    """
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
    user = User.objects.create(
        username="match-user",
        display_name="Old Name",
        email="old@example.com",
        phone="13900000000",
        password="",
        domain="domain.com",
    )
    runtime_result = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"user_id": "match-user", "name": "New Name", "email": "new@example.com", "mobile": "13800000000"}},
    )

    with patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute", return_value=runtime_result), patch(
        "apps.system_mgmt.nats_api.get_user_login_token",
        return_value={"result": True, "data": {"token": "login-token", "username": "match-user"}},
    ):
        result = login_with_binding(binding.id, "auth-code")

    user.refresh_from_db()
    # 登录认证不修改 display_name / email / phone(新策略)
    assert user.display_name == "Old Name"
    assert user.email == "old@example.com"
    assert user.phone == "13900000000"
    assert result["result"] is True


@pytest.mark.django_db
def test_get_active_login_auth_bindings_keeps_ready_wechat_binding_without_login_module():
    instance = IntegrationInstance.objects.create(
        name="微信开放平台",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="微信登录",
        integration_instance=instance,
        enabled=True,
        external_field="open_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsGuests",
    )

    bindings = get_active_login_auth_bindings()

    instance.refresh_from_db()
    binding.refresh_from_db()
    assert [item.id for item in bindings] == [binding.id]
    assert instance.enabled is True
    assert binding.enabled is True


# ---------- login_with_binding 日志分级（按错误码区分 WARNING / ERROR / INFO）----------

import logging as _logging


@pytest.mark.django_db
def test_login_with_binding_logs_warning_when_binding_not_found(caplog):
    """binding_id 不存在 → WARNING（业务查询 miss，可能合法场景）。"""
    with caplog.at_level(_logging.WARNING, logger="system-manager"):
        result = login_with_binding(999999, "auth-code")

    assert result["result"] is False
    assert result["message"] == "Login auth binding not found"
    warning_records = [r for r in caplog.records if r.levelno == _logging.WARNING]
    assert any(
        "binding not found" in r.message and "binding_id=999999" in r.message
        for r in warning_records
    ), f"Expected WARNING about missing binding, got: {[r.message for r in caplog.records]}"


@pytest.mark.django_db
def test_login_with_binding_logs_warning_when_binding_not_ready(caplog):
    """binding 状态不是 ready → WARNING（状态不一致）。"""
    instance = IntegrationInstance.objects.create(
        name="Feishu Login",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.PENDING_VERIFICATION},
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

    with caplog.at_level(_logging.WARNING, logger="system-manager"):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is False
    warning_records = [r for r in caplog.records if r.levelno == _logging.WARNING]
    assert any(
        "not ready" in r.message and f"binding_id={binding.id}" in r.message
        and "provider_key=feishu" in r.message
        for r in warning_records
    ), f"Expected WARNING with binding_id context, got: {[r.message for r in caplog.records]}"


@pytest.mark.django_db
def test_login_with_binding_logs_error_when_runtime_authenticate_fails(caplog):
    """runtime.execute 返回 failed_result → ERROR（外部 API 失败值得运维告警）。

    关键回归：今天发现的「AD user not found」bug 之前完全没记日志，这条 ERROR
    是定位 platform vs external 故障的第一信号。
    """
    instance = IntegrationInstance.objects.create(
        name="AD Login",
        provider_key="ad",
        config={"base_dn": "DC=corp,DC=com"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="AD Binding",
        integration_instance=instance,
        enabled=True,
        external_field="sAMAccountName",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    runtime_result = CapabilityExecutionResult.failed_result(
        "AD user not found", code="provider.auth_failed", field="sAMAccountName"
    )

    with caplog.at_level(_logging.ERROR, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ):
        result = login_with_binding(binding.id, "auth-code", username="zhangsan", password="x")

    assert result["result"] is False
    error_records = [r for r in caplog.records if r.levelno == _logging.ERROR]
    assert any(
        "binding_id=" in r.message
        and "provider_key=ad" in r.message
        and "provider.auth_failed" in r.message
        and 'username=' in r.message
        for r in error_records
    ), f"Expected ERROR with full context, got: {[r.message for r in caplog.records]}"


@pytest.mark.django_db
def test_login_with_binding_logs_warning_when_no_matching_platform_user(caplog):
    """外部用户成功认证但本地无匹配 → WARNING（配置 / 业务逻辑错）。"""
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
    runtime_result = CapabilityExecutionResult.success_result("ok", payload={"external_user": {"user_id": "ghost"}})

    with caplog.at_level(_logging.WARNING, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is False
    assert result["message"] == "No matching platform user found"
    warning_records = [r for r in caplog.records if r.levelno == _logging.WARNING]
    assert any(
        "no matching platform user" in r.message
        and f"binding_id={binding.id}" in r.message
        for r in warning_records
    ), f"Expected WARNING about missing user, got: {[r.message for r in caplog.records]}"


@pytest.mark.django_db
def test_login_with_binding_logs_info_on_successful_login(caplog):
    """成功登录 → INFO（audit trail）。"""
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
    user = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        phone="13800000000",
        password="",
        domain="domain.com",
    )
    runtime_result = CapabilityExecutionResult.success_result(
        "ok", payload={"external_user": {"user_id": "alice"}}
    )

    with caplog.at_level(_logging.INFO, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        return_value=runtime_result,
    ), patch(
        "apps.system_mgmt.nats_api.get_user_login_token",
        return_value={"result": True, "data": {"token": "login-token", "username": "alice"}},
    ):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    info_records = [r for r in caplog.records if r.levelno == _logging.INFO]
    assert any(
        "login_with_binding succeeded" in r.message
        and f"binding_id={binding.id}" in r.message
        and "username=alice" in r.message
        for r in info_records
    ), f"Expected INFO audit trail, got: {[r.message for r in caplog.records]}"

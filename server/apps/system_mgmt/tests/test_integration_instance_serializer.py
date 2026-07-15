from unittest.mock import ANY, patch

import pytest

from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices
from apps.system_mgmt.serializers import IntegrationInstanceSerializer


class FakeField:
    def __init__(
        self,
        key,
        *,
        required=False,
        secret=False,
        write_only=False,
        mask_strategy="full",
        reset_capabilities=None,
    ):
        self.key = key
        self.required = required
        self.secret = secret
        self.write_only = write_only
        self.mask_strategy = mask_strategy
        self.reset_capabilities = reset_capabilities or []


class FakeCapability:
    def __init__(self, key, connection_template=None):
        self.key = key
        self.connection_template = connection_template or []


class FakeManifest:
    def __init__(self, instance_template=None, capabilities=None, name=None):
        self.key = "feishu"
        self.name = name or "feishu"
        self.instance_template = instance_template or []
        self.capabilities = capabilities or []

    def get_all_connection_fields(self):
        fields = list(self.instance_template)
        for capability in self.capabilities:
            fields.extend(capability.connection_template)
        return fields

    def get_scoped_connection_fields(self, config_scope=""):
        if not config_scope:
            return self.get_all_connection_fields()
        if config_scope == "base":
            return list(self.instance_template)
        for capability in self.capabilities:
            if capability.key == config_scope:
                return list(self.instance_template) + list(capability.connection_template)
        return list(self.instance_template)

    def get_secret_fields(self):
        return [field for field in self.get_all_connection_fields() if field.secret or field.write_only]


class FakeRegistry:
    def __init__(self, manifest):
        self.manifest = manifest

    def get(self, provider_key):
        if provider_key == self.manifest.key:
            return self.manifest
        return None


def patch_provider_registry(monkeypatch, manifest):
    registry = FakeRegistry(manifest)
    monkeypatch.setattr(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_provider_registry",
        lambda: registry,
    )
    monkeypatch.setattr("apps.system_mgmt.providers.get_provider_registry", lambda: registry)


@pytest.mark.django_db
def test_integration_instance_serializer_allows_draft_create_without_required_config():
    serializer = IntegrationInstanceSerializer(
        data={
            "name": "finance-feishu",
            "provider_key": "feishu",
            "description": "用于财务审批消息推送与单点登录",
            "team": [],
            "config": {},
            "is_draft": True,
        }
    )

    assert serializer.is_valid(), serializer.errors
    instance = serializer.save()

    assert instance.status == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
    assert instance.capability_status == {
        "login_auth": IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
        "user_sync": IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
        "im_notification": IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
    }
    assert instance.capability_enabled == {
        "login_auth": True,
        "user_sync": True,
        "im_notification": True,
    }


@pytest.mark.django_db
def test_integration_instance_serializer_requires_required_config_for_non_draft_create():
    serializer = IntegrationInstanceSerializer(
        data={
            "name": "finance-feishu",
            "provider_key": "feishu",
            "description": "用于财务审批消息推送与单点登录",
            "team": [],
            "config": {},
        }
    )

    assert serializer.is_valid() is False
    assert "config" in serializer.errors


@pytest.mark.django_db
def test_integration_instance_serializer_requires_required_capability_connection_fields(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[
            FakeCapability("user_sync", connection_template=[FakeField("user_sync_api_url", required=True)]),
        ],
    )
    patch_provider_registry(monkeypatch, manifest)

    serializer = IntegrationInstanceSerializer(
        data={
            "name": "finance-feishu",
            "provider_key": "feishu",
            "description": "用于财务审批消息推送与单点登录",
            "team": [],
            "config": {"app_id": "cli_xxx"},
        }
    )

    assert serializer.is_valid() is False
    assert "config" in serializer.errors
    assert "user_sync_api_url" in str(serializer.errors["config"])


@pytest.mark.django_db
def test_integration_instance_serializer_scoped_update_only_resets_target_capability(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[
            FakeCapability("login_auth", connection_template=[FakeField("login_api_url")]),
            FakeCapability("user_sync", connection_template=[FakeField("user_sync_api_url")]),
        ],
    )
    patch_provider_registry(monkeypatch, manifest)

    instance = IntegrationInstance.objects.create(
        name="finance-feishu",
        provider_key="feishu",
        description="用于财务审批消息推送与单点登录",
        config={"app_id": "cli_xxx", "login_api_url": "https://login", "user_sync_api_url": "https://sync-old"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.READY,
        },
    )

    serializer = IntegrationInstanceSerializer(
        instance=instance,
        data={
            "config_scope": "user_sync",
            "config": {"user_sync_api_url": "https://sync-new"},
        },
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.capability_status["user_sync"] == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
    assert updated.capability_status["login_auth"] == IntegrationInstanceStatusChoices.READY


@pytest.mark.django_db
def test_integration_instance_serializer_rejects_invalid_capability_enabled_keys(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[
            FakeCapability("login_auth"),
            FakeCapability("user_sync"),
        ],
    )
    patch_provider_registry(monkeypatch, manifest)

    instance = IntegrationInstance.objects.create(
        name="finance-feishu",
        provider_key="feishu",
        description="用于财务审批消息推送与单点登录",
        config={"app_id": "cli_xxx"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.READY,
        },
        capability_enabled={"login_auth": True, "user_sync": True},
    )

    serializer = IntegrationInstanceSerializer(
        instance=instance,
        data={"capability_enabled": {"login_auth": True, "nonexistent": False}},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert "capability_enabled" in serializer.errors


@pytest.mark.django_db
def test_integration_instance_serializer_rejects_invalid_json_contract_values(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[
            FakeCapability("login_auth"),
            FakeCapability("user_sync"),
        ],
    )
    patch_provider_registry(monkeypatch, manifest)

    serializer = IntegrationInstanceSerializer(
        data={
            "name": "finance-feishu",
            "provider_key": "feishu",
            "team": [],
            "config": ["not", "an", "object"],
            "capability_status": {"login_auth": "unknown"},
            "capability_enabled": {"login_auth": "yes"},
        }
    )

    assert serializer.is_valid() is False
    assert "config" in serializer.errors
    assert "capability_status" in serializer.errors
    assert "capability_enabled" in serializer.errors


@pytest.mark.django_db
def test_integration_instance_serializer_rejects_invalid_capability_status_keys(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[FakeCapability("login_auth")],
    )
    patch_provider_registry(monkeypatch, manifest)

    serializer = IntegrationInstanceSerializer(
        data={
            "name": "finance-feishu",
            "provider_key": "feishu",
            "team": [],
            "config": {"app_id": "cli_xxx"},
            "capability_status": {"nonexistent": IntegrationInstanceStatusChoices.READY},
        }
    )

    assert serializer.is_valid() is False
    assert "capability_status" in serializer.errors


@pytest.mark.django_db
def test_integration_instance_serializer_display_name(monkeypatch):
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[FakeCapability("login_auth")],
    )
    patch_provider_registry(monkeypatch, manifest)

    instance = IntegrationInstance.objects.create(
        name="总部通讯录",
        provider_key="feishu",
        description="",
        config={"app_id": "cli_xxx"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
    )

    serializer = IntegrationInstanceSerializer(instance)
    assert serializer.data["display_name"] == "总部通讯录(feishu)"


# ----------------------------------------------------------------------
# login_auth_callback_url 字段的 redirect_origin 透传契约
# ----------------------------------------------------------------------


@pytest.fixture
def login_auth_ready_instance(db, monkeypatch):
    """构造一个声明了 login_auth 能力的集成实例,并为 serializer 测试打桩 provider registry。"""
    manifest = FakeManifest(
        instance_template=[FakeField("app_id", required=True)],
        capabilities=[FakeCapability("login_auth")],
    )
    patch_provider_registry(monkeypatch, manifest)
    return IntegrationInstance.objects.create(
        name="feishu-login",
        provider_key="feishu",
        config={"app_id": "cli_xxx"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"login_auth": True},
    )


@pytest.mark.django_db
def test_login_auth_callback_url_forwards_redirect_origin_from_context(
    login_auth_ready_instance, request_factory,
):
    """S1:redirect_origin 为 None 时,生成函数收到 None,行为向后兼容。"""
    request = request_factory.get("/")

    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri",
        return_value="http://fallback/api/v1/core/api/login_auth/callback/",
    ) as mock_cb:
        serializer = IntegrationInstanceSerializer(
            login_auth_ready_instance,
            context={"request": request, "redirect_origin": None},
        )
        value = serializer.data["login_auth_callback_url"]

    assert value == "http://fallback/api/v1/core/api/login_auth/callback/"
    mock_cb.assert_called_once_with(request=request, redirect_origin=None)


@pytest.mark.django_db
def test_login_auth_callback_url_passes_through_same_origin_redirect_origin(
    login_auth_ready_instance, request_factory,
):
    """S2:同源 redirect_origin 原样透传给生成函数。"""
    request = request_factory.get("/")

    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri",
        return_value="http://testserver/api/v1/core/api/login_auth/callback/",
    ) as mock_cb:
        serializer = IntegrationInstanceSerializer(
            login_auth_ready_instance,
            context={"request": request, "redirect_origin": "http://testserver"},
        )
        value = serializer.data["login_auth_callback_url"]

    assert value.endswith("/api/v1/core/api/login_auth/callback/")
    mock_cb.assert_called_once_with(request=request, redirect_origin="http://testserver")


@pytest.mark.django_db
def test_login_auth_callback_url_normalizes_empty_redirect_origin_to_none(
    login_auth_ready_instance, request_factory,
):
    """S3:空串统一归一化为 None,避免函数被同源校验空检后再降级。"""
    request = request_factory.get("/")

    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri",
        return_value="http://fallback/api/v1/core/api/login_auth/callback/",
    ) as mock_cb:
        serializer = IntegrationInstanceSerializer(
            login_auth_ready_instance,
            context={"request": request, "redirect_origin": ""},
        )
        serializer.data["login_auth_callback_url"]

    mock_cb.assert_called_once_with(request=request, redirect_origin=None)


@pytest.mark.django_db
def test_login_auth_callback_url_passes_through_cross_origin_redirect_origin(
    login_auth_ready_instance, request_factory,
):
    """S4:跨域 redirect_origin 仍按契约透传给生成函数;具体降级由生成函数负责。"""
    request = request_factory.get("/")

    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri",
        return_value="http://testserver/api/v1/core/api/login_auth/callback/",
    ) as mock_cb:
        serializer = IntegrationInstanceSerializer(
            login_auth_ready_instance,
            context={"request": request, "redirect_origin": "http://evil.com"},
        )
        serializer.data["login_auth_callback_url"]

    mock_cb.assert_called_once_with(request=request, redirect_origin="http://evil.com")


@pytest.mark.django_db
def test_login_auth_callback_url_returns_empty_when_capability_not_declared(
    db, request_factory,
):
    """S5:实例未声明 login_auth 能力时,不调用生成函数,字段直接返回空串。"""
    request = request_factory.get("/")
    instance = IntegrationInstance.objects.create(
        name="no-login",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"user_sync": IntegrationInstanceStatusChoices.READY},
        capability_enabled={"user_sync": True},
    )

    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.get_login_auth_callback_uri",
    ) as mock_cb:
        serializer = IntegrationInstanceSerializer(
            instance,
            context={"request": request, "redirect_origin": "http://testserver"},
        )
        value = serializer.data["login_auth_callback_url"]

    assert value == ""
    mock_cb.assert_not_called()


@pytest.mark.django_db
def test_update_base_dn_resets_login_auth_to_pending_verification(monkeypatch):
    """AD login_auth.connection_template 含 base_dn 时，更新 base_dn 应重置 login_auth，
    不动 user_sync。回归 2026-07-13 spec。

    本测试只验证序列化器行为，不改生产代码：依赖 manifest 字段 reset_capabilities
    自动 fallback 到 [capability.key] 的契约（schemas.py + serializer）。
    """
    manifest = FakeManifest(
        instance_template=[
            FakeField("connection_url", required=True),
            FakeField("bind_dn", required=True),
            FakeField("bind_password", required=True),
        ],
        capabilities=[
            FakeCapability(
                "login_auth",
                connection_template=[
                    FakeField("base_dn", required=True),
                    FakeField("login_auth_identity_field", required=True),
                ],
            ),
            FakeCapability("user_sync", connection_template=[]),
        ],
    )
    manifest.key = "ad"  # 与 instance.provider_key 对齐
    manifest.name = "ad"
    patch_provider_registry(monkeypatch, manifest)

    instance = IntegrationInstance.objects.create(
        name="corp-ad",
        provider_key="ad",
        description="AD 集成",
        config={
            "connection_url": "ad.example.com",
            "bind_dn": "CN=svc,DC=corp,DC=example,DC=com",
            "bind_password": "secret",
            "base_dn": "DC=old,DC=example,DC=com",
            "login_auth_identity_field": "sAMAccountName",
        },
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.READY,
        },
    )

    serializer = IntegrationInstanceSerializer(
        instance=instance,
        data={
            "config_scope": "login_auth",
            "config": {"base_dn": "DC=new,DC=example,DC=com"},
        },
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.capability_status["login_auth"] == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
    assert updated.capability_status["user_sync"] == IntegrationInstanceStatusChoices.READY

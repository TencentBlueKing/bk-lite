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

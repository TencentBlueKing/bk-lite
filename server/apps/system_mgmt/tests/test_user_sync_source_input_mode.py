import pytest
from unittest.mock import patch
from apps.system_mgmt.models import IntegrationInstance
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.providers.schemas import ProviderManifest
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncSourceSerializer
from apps.system_mgmt.services.user_sync_service import (
    get_user_sync_root_department_input_mode,
    get_user_sync_root_scope_field,
)


@pytest.fixture
def ready_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-sync",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready", "login_auth": "pending_verification", "im_notification": "pending_verification"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def ready_ad_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="ad-sync",
        provider_key="ad",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready", "login_auth": "ready"},
        config={
            "connection_url": "ldap://ad.example.com:389",
            "ssl_encryption": "none",
            "timeout": 10,
            "bind_dn": "CN=svc,OU=Service,DC=corp,DC=example,DC=com",
            "bind_password": "secret",
            "base_dn": "DC=corp,DC=example,DC=com",
        },
    )


def test_mode_resolver_defaults_to_department_select_for_unknown_provider():
    assert get_user_sync_root_department_input_mode("nonexistent_provider") == "department_select"


def test_mode_resolver_reads_manual_input_from_manifest():
    manifest = ProviderManifest.model_validate(
        {
            "key": "demo_manual",
            "name": "Demo Manual",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "demo_manual.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )
    from apps.system_mgmt.providers.registry import get_provider_registry, get_capability_adapter_registry
    from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter

    registry = get_provider_registry()
    adapter_registry = get_capability_adapter_registry()
    registry.register(manifest)
    adapter_registry.register("demo_manual.user_sync", BaseUserSyncAdapter)

    try:
        assert get_user_sync_root_department_input_mode("demo_manual") == "manual_input"
    finally:
        registry._providers.pop("demo_manual", None)
        adapter_registry._adapters.pop("demo_manual.user_sync", None)


def test_ad_root_scope_field_resolves_to_root_dn():
    assert get_user_sync_root_scope_field("ad") == "root_dn"


def test_ad_root_dn_uses_manual_input_mode():
    assert get_user_sync_root_department_input_mode("ad") == "manual_input"


@pytest.fixture
def manual_input_instance(db):
    from apps.system_mgmt.providers.registry import get_provider_registry, get_capability_adapter_registry
    from apps.system_mgmt.providers.adapters.base import BaseUserSyncAdapter
    from apps.system_mgmt.providers.schemas import ProviderManifest

    manifest = ProviderManifest.model_validate(
        {
            "key": "test_manual",
            "name": "Test Manual",
            "business_templates": {
                "user_sync_form": {
                    "title": "User Sync",
                    "groups": [
                        {
                            "key": "pull",
                            "title": "拉取配置",
                            "fields": [
                                {
                                    "key": "root_department_id",
                                    "label": "同步范围",
                                    "required": True,
                                    "input_mode": "manual_input",
                                }
                            ],
                        }
                    ],
                    "available_external_fields": ["user_id"],
                }
            },
            "capabilities": [
                {
                    "key": "user_sync",
                    "name": "User Sync",
                    "adapter_key": "test_manual.user_sync",
                    "adapter_path": "apps.system_mgmt.providers.adapters.base.BaseUserSyncAdapter",
                    "business_template": "user_sync_form",
                }
            ],
        }
    )
    registry = get_provider_registry()
    adapter_registry = get_capability_adapter_registry()
    registry.register(manifest)
    adapter_registry.register("test_manual.user_sync", BaseUserSyncAdapter)

    instance = IntegrationInstance.objects.create(
        name="test-manual",
        provider_key="test_manual",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    yield instance
    registry._providers.pop("test_manual", None)
    adapter_registry._adapters.pop("test_manual.user_sync", None)


@pytest.mark.django_db
def test_manual_input_accepts_raw_scope_and_skips_list_departments(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "ou=paas,dc=bktest,dc=com",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute") as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_not_called()
    assert serializer.validated_data["business_config"]["root_department_id"] == "ou=paas,dc=bktest,dc=com"


@pytest.mark.django_db
def test_manual_input_ignores_department_id_type(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "ou=paas,dc=bktest,dc=com",
                "department_id_type": "department_id",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute") as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_not_called()
    assert "department_id_type" not in serializer.validated_data["business_config"]


@pytest.mark.django_db
def test_manual_input_rejects_empty_root_department(manual_input_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "manual-source",
            "integration_instance": manual_input_instance.id,
            "root_group_name": "Manual Root",
            "business_config": {
                "root_department_id": "",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    assert serializer.is_valid() is False
    assert "business_config" in serializer.errors


@pytest.mark.django_db
def test_ad_manual_input_accepts_root_dn_and_skips_department_listing(ready_ad_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "ad-source",
            "integration_instance": ready_ad_integration_instance.id,
            "root_group_name": "AD Root",
            "business_config": {
                "root_dn": "OU=PAAS,DC=corp,DC=example,DC=com",
            },
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute") as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_not_called()
    assert serializer.validated_data["business_config"]["root_dn"] == "OU=PAAS,DC=corp,DC=example,DC=com"


@pytest.mark.django_db
def test_ad_manual_input_accepts_root_dn_equal_to_base_dn(ready_ad_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "ad-source",
            "integration_instance": ready_ad_integration_instance.id,
            "root_group_name": "AD Root",
            "business_config": {
                "root_dn": "DC=corp,DC=example,DC=com",
            },
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_ad_manual_input_accepts_root_dn_within_base_dn(ready_ad_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "ad-source",
            "integration_instance": ready_ad_integration_instance.id,
            "root_group_name": "AD Root",
            "business_config": {
                "root_dn": "OU=PAAS,DC=corp,DC=example,DC=com",
            },
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_ad_manual_input_accepts_root_dn_outside_base_dn(ready_ad_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "ad-source",
            "integration_instance": ready_ad_integration_instance.id,
            "root_group_name": "AD Root",
            "business_config": {
                "root_dn": "OU=PAAS,DC=other,DC=example,DC=com",
            },
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_department_options_returns_400_for_manual_input_provider(api_client, authenticated_user, manual_input_instance):
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/department_options/",
        {"integration_instance": manual_input_instance.id},
    )

    assert response.status_code == 400
    assert "manual_input" in response.json()["message"] or "部门树" in response.json()["message"]


@pytest.mark.django_db
def test_department_select_still_calls_list_departments_and_normalizes_all(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "feishu-source",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "root_department_id": "__all__",
                "department_id_type": "department_id",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
            ],
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        assert serializer.is_valid(), serializer.errors

    mock_execute.assert_called_once()
    assert serializer.validated_data["business_config"]["root_department_id"] == "0"


@pytest.mark.django_db
def test_department_select_rejects_invalid_department(ready_integration_instance):
    serializer = UserSyncSourceSerializer(
        data={
            "name": "feishu-source",
            "integration_instance": ready_integration_instance.id,
            "root_group_name": "Feishu Root",
            "business_config": {
                "root_department_id": "stale-dept",
            },
            "field_mapping": {"username": "user_id"},
            "schedule_config": {"mode": "disabled"},
        }
    )

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [
                {"id": "__all__", "name": "全部部门", "parent_id": None, "children": []},
            ],
        },
    )

    with patch("apps.system_mgmt.providers.runtime.RuntimeApplicationService.execute", return_value=payload):
        assert serializer.is_valid() is False

    assert "business_config" in serializer.errors

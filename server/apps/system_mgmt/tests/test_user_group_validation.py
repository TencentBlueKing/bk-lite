import pytest

from apps.core.utils.loader import LanguageLoader
from apps.system_mgmt.models import Group
from apps.system_mgmt.viewset import user_viewset


@pytest.mark.django_db
def test_validate_selected_groups_rejects_empty_selection():
    loader = LanguageLoader(app="system_mgmt", default_lang="en")

    message = user_viewset._validate_selected_groups([], loader)

    assert message == "At least one group must be selected"


@pytest.mark.django_db
def test_validate_selected_groups_rejects_invalid_group_ids():
    loader = LanguageLoader(app="system_mgmt", default_lang="en")
    normal_group = Group.objects.create(name="Normal Group", parent_id=0, is_virtual=False)

    message = user_viewset._validate_selected_groups([normal_group.id, 999999], loader)

    assert message == "Invalid group IDs: [999999]"


@pytest.mark.django_db
def test_validate_selected_groups_rejects_virtual_only_selection_in_zh():
    loader = LanguageLoader(app="system_mgmt", default_lang="zh-Hans")
    guest_group = Group.objects.create(name="OpsPilotGuest", parent_id=0, is_virtual=True)

    message = user_viewset._validate_selected_groups([guest_group.id], loader)

    assert message == "至少选择一个普通组织"


@pytest.mark.django_db
def test_validate_selected_groups_accepts_selection_with_normal_group():
    loader = LanguageLoader(app="system_mgmt", default_lang="en")
    guest_group = Group.objects.create(name="OpsPilotGuest", parent_id=0, is_virtual=True)
    normal_group = Group.objects.create(name="Normal Group", parent_id=0, is_virtual=False)

    message = user_viewset._validate_selected_groups([guest_group.id, normal_group.id], loader)

    assert message is None


@pytest.mark.django_db
def test_system_mgmt_exports_provider_and_integration_instance_models():
    from apps.system_mgmt.models import IntegrationInstance
    from apps.system_mgmt.providers import get_provider_registry
    from apps.system_mgmt.providers.registry import ProviderRegistry

    assert isinstance(get_provider_registry(), ProviderRegistry)
    assert IntegrationInstance._meta.model_name == "integrationinstance"


@pytest.mark.django_db
def test_integration_instance_encrypts_config_secret_field_roundtrip():
    """IntegrationInstance 通过 EncryptMixin 手动加密 config 中的 secret 字段。

    Provider 在 feature-lz 重构后不再是 Django Model,而是 ProviderRegistry
    注册表;IntegrationInstance 的 config 字段不再由 ORM 自动加密,
    而是由调用方在写入前调用 encrypt_field,读取时调用 decrypt_field。
    这里验证 encrypt/decrypt 是互逆的、且加密后密文不再等于明文。
    """
    from apps.system_mgmt.models import IntegrationInstance

    instance = IntegrationInstance(provider_key="feishu", config={})
    config = {"app_secret": "plain-secret", "tenant_key": "tenant-key"}

    instance.encrypt_field("app_secret", config)

    assert config["app_secret"] != "plain-secret"
    assert config["tenant_key"] == "tenant-key"

    instance.decrypt_field("app_secret", config)

    assert config["app_secret"] == "plain-secret"

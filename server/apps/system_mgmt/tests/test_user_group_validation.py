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
    from apps.system_mgmt.models import IntegrationInstance, Provider

    assert Provider._meta.model_name == "provider"
    assert IntegrationInstance._meta.model_name == "integrationinstance"


@pytest.mark.django_db
def test_integration_instance_encrypts_shared_app_secret():
    from apps.system_mgmt.models import IntegrationInstance, Provider

    provider = Provider.objects.create(
        provider_key="feishu",
        display_name="Feishu",
        capabilities=["login_auth", "user_sync", "im_notification"],
        manifest={},
    )

    instance = IntegrationInstance.objects.create(
        provider=provider,
        name="feishu-default",
        config={"app_secret": "plain-secret", "tenant_key": "tenant-key"},
    )

    assert instance.config["app_secret"] != "plain-secret"

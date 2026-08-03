from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.system_mgmt.models import Group, IntegrationInstance, Role, User, UserSyncSource


pytestmark = pytest.mark.django_db

BASE = "/api/v1/system_mgmt/user"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="synced-user-guard-admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.group_list = [{"id": 1, "name": "Default"}]
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def synced_user(db):
    instance = IntegrationInstance.objects.create(
        name="synced-user-guard-instance",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready"},
        config={},
    )
    source = UserSyncSource.objects.create(
        name="synced-user-guard-source",
        integration_instance=instance,
        root_group_name="同步用户根组织",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
    )
    group = Group.objects.create(name="同步用户组织", parent_id=0, sync_source=source)
    return User.objects.create(
        username="synced-user-guard",
        display_name="同步用户",
        email="synced-user@example.com",
        phone="13800000000",
        password="x",
        group_list=[group.id],
        sync_source=source,
    )


@pytest.fixture(autouse=True)
def _patch_externals():
    with patch("apps.system_mgmt.viewset.user_viewset.log_operation"), patch(
        "apps.system_mgmt.viewset.user_viewset.CMDB"
    ):
        yield


def test_update_synced_user_preserves_basic_information_and_organization(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    platform_role = Role.objects.create(name="synced-user-platform-role", app="cmdb")

    response = super_client.post(
        f"{BASE}/update_user/",
        {
            "user_id": synced_user.id,
            "username": synced_user.username,
            "lastName": "不允许修改的姓名",
            "email": "changed@example.com",
            "phone": "13900000000",
            "locale": "en",
            "timezone": "UTC",
            "groups": [],
            "roles": [platform_role.id],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert synced_user.display_name == "同步用户"
    assert synced_user.email == "synced-user@example.com"
    assert synced_user.phone == "13800000000"
    assert synced_user.group_list != []
    assert synced_user.locale == "en"
    assert synced_user.timezone == "UTC"
    assert synced_user.role_list == [platform_role.id]


def test_create_local_user_in_synced_group_is_rejected(super_client, synced_user):
    synced_group_id = synced_user.group_list[0]

    response = super_client.post(
        f"{BASE}/create_user/",
        {
            "username": "local-user-in-synced-group",
            "lastName": "本地用户",
            "email": "local-user@example.com",
            "phone": "13800000001",
            "locale": "en",
            "timezone": "UTC",
            "groups": [synced_group_id],
            "roles": [],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )

    assert response.json()["result"] is False
    assert not User.objects.filter(username="local-user-in-synced-group").exists()


def test_update_local_user_cannot_change_synced_group_membership(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    local_group = Group.objects.create(name="本地组织", parent_id=0)
    local_user = User.objects.create(
        username="local-user-with-synced-group",
        display_name="本地用户",
        email="local-user@example.com",
        phone="13800000002",
        password="x",
        locale="en",
        timezone="UTC",
        group_list=synced_user.group_list,
    )

    response = super_client.post(
        f"{BASE}/update_user/",
        {
            "user_id": local_user.id,
            "username": local_user.username,
            "lastName": local_user.display_name,
            "email": local_user.email,
            "phone": local_user.phone,
            "locale": "en",
            "timezone": "UTC",
            "groups": [local_group.id],
            "roles": [],
            "rules": [],
            "is_superuser": False,
        },
        format="json",
    )

    local_user.refresh_from_db()
    assert response.json()["result"] is False
    assert local_user.group_list == synced_user.group_list

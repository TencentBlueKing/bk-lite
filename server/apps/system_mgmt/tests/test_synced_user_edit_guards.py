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


def _update_user_payload(user, **overrides):
    payload = {
        "user_id": user.id,
        "username": user.username,
        "lastName": user.display_name,
        "email": user.email,
        "phone": user.phone,
        "locale": "en",
        "timezone": "UTC",
        "groups": user.group_list,
        "roles": [],
        "rules": [],
        "is_superuser": False,
    }
    payload.update(overrides)
    return payload


def _create_local_user(suffix):
    Role.objects.get_or_create(name="admin", app="")
    local_group = Group.objects.create(name=f"本地用户组织-{suffix}", parent_id=0)
    return User.objects.create(
        username=f"local-user-{suffix}",
        display_name="本地用户",
        email=f"local-{suffix}@example.com",
        phone="13800000003",
        password="x",
        locale="en",
        timezone="UTC",
        group_list=[local_group.id],
    )


def test_update_synced_user_preserves_name_and_organization_but_allows_contact_change(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    platform_role = Role.objects.create(name="synced-user-platform-role", app="cmdb")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(
            synced_user,
            lastName="不允许修改的姓名",
            email="  changed@example.com  ",
            phone=" 13900000000 ",
            groups=[],
            roles=[platform_role.id],
        ),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert synced_user.display_name == "同步用户"
    assert synced_user.email == "changed@example.com"
    assert synced_user.phone == "13900000000"
    assert synced_user.group_list != []
    assert synced_user.locale == "en"
    assert synced_user.timezone == "UTC"
    assert synced_user.role_list == [platform_role.id]


def test_update_synced_user_rejects_empty_email(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(synced_user, email="  "),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.status_code == 400
    assert response.json() == {"result": False, "message": "Email cannot be empty"}
    assert synced_user.email == "synced-user@example.com"


def test_update_synced_user_rejects_invalid_phone(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(synced_user, phone="not-a-phone"),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.status_code == 400
    assert response.json() == {"result": False, "message": "Invalid phone number format"}
    assert synced_user.phone == "13800000000"


def test_update_synced_user_rejects_non_string_email(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(synced_user, email=["not-a-string"]),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.status_code == 400
    assert response.json() == {"result": False, "message": "Email cannot be empty"}
    assert synced_user.email == "synced-user@example.com"


def test_update_synced_user_can_fill_empty_contact_fields(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    synced_user.email = ""
    synced_user.phone = ""
    synced_user.save(update_fields=["email", "phone"])

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(synced_user, email="filled@example.com", phone="13600000000"),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert synced_user.email == "filled@example.com"
    assert synced_user.phone == "13600000000"


def test_update_synced_user_omits_email_and_phone_when_not_submitted(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    platform_role = Role.objects.create(name="synced-user-omit-role", app="cmdb")
    payload = _update_user_payload(
        synced_user,
        locale="en",
        timezone="UTC",
        roles=[platform_role.id],
    )
    payload.pop("email")
    payload.pop("phone")

    response = super_client.post(f"{BASE}/update_user/", payload, format="json")

    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert synced_user.email == "synced-user@example.com"
    assert synced_user.phone == "13800000000"
    assert synced_user.role_list == [platform_role.id]


def test_update_synced_user_allows_retained_archived_groups(super_client, synced_user):
    Role.objects.get_or_create(name="admin", app="")
    archived = Group.objects.create(name="synced-user-archived-keep", parent_id=0, is_delete=True)
    synced_user.group_list = list(synced_user.group_list) + [archived.id]
    synced_user.save(update_fields=["group_list"])
    platform_role = Role.objects.create(name="synced-user-archived-role", app="cmdb")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(
            synced_user,
            lastName="不允许修改的姓名",
            email="changed@example.com",
            phone="13900000000",
            groups=[],
            roles=[platform_role.id],
        ),
        format="json",
    )

    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert archived.id in synced_user.group_list
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


def test_update_local_user_strips_contact_fields_on_write(super_client):
    local_user = _create_local_user("contact-strip")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(
            local_user,
            email="  local-stripped@example.com  ",
            phone=" 13800000003 ",
        ),
        format="json",
    )

    local_user.refresh_from_db()
    assert response.json()["result"] is True
    assert local_user.email == "local-stripped@example.com"
    assert local_user.phone == "13800000003"


def test_update_local_user_rejects_empty_email(super_client):
    local_user = _create_local_user("empty-email")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(local_user, email="  "),
        format="json",
    )

    local_user.refresh_from_db()
    assert response.status_code == 400
    assert response.json() == {"result": False, "message": "Email cannot be empty"}
    assert local_user.email == "local-empty-email@example.com"


def test_update_local_user_rejects_non_string_email(super_client):
    local_user = _create_local_user("non-string-email")

    response = super_client.post(
        f"{BASE}/update_user/",
        _update_user_payload(local_user, email=["not-a-string"]),
        format="json",
    )

    local_user.refresh_from_db()
    assert response.status_code == 400
    assert response.json() == {"result": False, "message": "Email cannot be empty"}
    assert local_user.email == "local-non-string-email@example.com"

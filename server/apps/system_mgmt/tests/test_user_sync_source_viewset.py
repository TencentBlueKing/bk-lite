from unittest.mock import patch

import pytest

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncSource


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
def user_sync_source(ready_integration_instance):
    return UserSyncSource.objects.create(
        name="source-a",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Root A",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={},
    )


@pytest.mark.django_db
def test_sync_now_rejects_disabled_source(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])
    api_client.cookies["current_team"] = "1"

    user_sync_source.enabled = False
    user_sync_source.save(update_fields=["enabled"])

    with patch("apps.system_mgmt.viewset.user_sync_source_viewset.sync_source_now") as mock_sync_now:
        response = api_client.post(f"/api/v1/system_mgmt/user_sync_source/{user_sync_source.id}/sync_now/")

    assert response.status_code == 400
    assert response.json()["result"] is False
    mock_sync_now.assert_not_called()


@pytest.mark.django_db
def test_destroy_deletes_root_subtree_and_users(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])
    api_client.cookies["current_team"] = "1"

    root_group = Group.objects.create(
        name="Root A",
        parent_id=0,
        sync_source=user_sync_source,
        external_id=f"user-sync:{user_sync_source.id}:0",
    )
    child_group = Group.objects.create(
        name="Dept A",
        parent_id=root_group.id,
        sync_source=user_sync_source,
        external_id=f"user-sync:{user_sync_source.id}:dept-a",
    )
    synced_user = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        phone="13800000000",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[child_group.id],
        sync_source=user_sync_source,
    )
    grouped_user = User.objects.create(
        username="bob",
        display_name="Bob",
        email="bob@example.com",
        phone="13800000001",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[child_group.id],
        sync_source=None,
    )

    response = api_client.delete(f"/api/v1/system_mgmt/user_sync_source/{user_sync_source.id}/")

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert UserSyncSource.objects.filter(id=user_sync_source.id).exists() is False
    assert Group.objects.filter(id__in=[root_group.id, child_group.id]).count() == 0
    assert User.objects.filter(id__in=[synced_user.id, grouped_user.id]).count() == 0


@pytest.mark.django_db
def test_destroy_deletes_source_even_without_root_group(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])
    api_client.cookies["current_team"] = "1"

    synced_user = User.objects.create(
        username="charlie",
        display_name="Charlie",
        email="charlie@example.com",
        phone="13800000002",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[],
        sync_source=user_sync_source,
    )

    response = api_client.delete(f"/api/v1/system_mgmt/user_sync_source/{user_sync_source.id}/")

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert UserSyncSource.objects.filter(id=user_sync_source.id).exists() is False
    assert User.objects.filter(id=synced_user.id).count() == 0

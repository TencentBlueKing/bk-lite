from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncRun, UserSyncSource
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.serializers.user_sync_source_serializer import UserSyncSourceSerializer
from apps.system_mgmt.services.user_sync_service import delete_user_sync_source
from apps.system_mgmt.utils.password_vault import encrypt_for_vault


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
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled", "timezone": "Asia/Shanghai"},
    )


@pytest.fixture
def ready_ad_integration_instance(db):
    return IntegrationInstance.objects.create(
        name="ad-sync",
        provider_key="ad",
        enabled=True,
        status="ready",
        capability_status={"user_sync": "ready", "login_auth": "ready"},
        config={"host": "ldap.example.com", "port": 389, "bind_dn": "CN=svc,DC=example,DC=com"},
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
def test_delete_user_sync_source_does_not_scan_all_users(user_sync_source):
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
        username="alice-service",
        display_name="Alice",
        email="alice-service@example.com",
        password="",
        domain="domain.com",
        group_list=[],
        sync_source=user_sync_source,
    )
    grouped_user = User.objects.create(
        username="bob-service",
        display_name="Bob",
        email="bob-service@example.com",
        password="",
        domain="domain.com",
        group_list=[child_group.id],
        sync_source=None,
    )

    with patch("apps.system_mgmt.services.user_sync_service.User.objects.all", side_effect=AssertionError("full user scan")):
        result = delete_user_sync_source(user_sync_source)

    assert result["result"] is True
    assert User.objects.filter(id__in=[synced_user.id, grouped_user.id]).count() == 0


@pytest.mark.django_db
def test_list_returns_explicit_root_scope_field(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.get("/api/v1/system_mgmt/user_sync_source/")

    assert response.status_code == 200
    payload = response.data if isinstance(response.data, list) else response.data.get("items", response.data.get("results"))
    assert payload[0]["root_scope_field"] == "root_department_id"


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


@pytest.mark.django_db
def test_create_source_logs_operation(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ), patch("apps.system_mgmt.viewset.user_sync_source_viewset.log_operation") as mock_log:
        response = api_client.post(
            "/api/v1/system_mgmt/user_sync_source/",
            {
                "name": "source-b",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "Root B",
                "business_config": {"root_department_id": "dept-root"},
                "field_mapping": {"username": "user_id"},
                "schedule_config": {"mode": "disabled", "timezone": "Asia/Shanghai"},
            },
            format="json",
        )

    assert response.status_code == 201
    assert UserSyncSource.objects.filter(name="source-b").exists() is True
    mock_log.assert_called_once()

@pytest.mark.django_db
def test_create_source_accepts_weekly_schedule_config(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        response = api_client.post(
            "/api/v1/system_mgmt/user_sync_source/",
            {
                "name": "source-weekly",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "Weekly Root",
                "business_config": {"root_department_id": "dept-root"},
                "field_mapping": {"username": "user_id"},
                "schedule_config": {
                    "mode": "weekly",
                    "time": "02:00",
                    "weekdays": [1, 3, 5],
                    "timezone": "Asia/Shanghai",
                },
            },
            format="json",
        )

    assert response.status_code == 201
    assert response.json()["data"]["schedule_config"]["mode"] == "weekly"


@pytest.mark.django_db
def test_create_source_rejects_legacy_schedule_payload(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        response = api_client.post(
            "/api/v1/system_mgmt/user_sync_source/",
            {
                "name": "source-legacy",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "Legacy Root",
                "business_config": {"root_department_id": "dept-root"},
                "field_mapping": {"username": "user_id"},
                "schedule_config": {"enabled": True, "sync_time": "02:00"},
            },
            format="json",
        )

    assert response.status_code == 400


@pytest.mark.django_db
def test_update_source_logs_operation(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ), patch("apps.system_mgmt.viewset.user_sync_source_viewset.log_operation") as mock_log:
        response = api_client.put(
            f"/api/v1/system_mgmt/user_sync_source/{user_sync_source.id}/",
            {
                "name": user_sync_source.name,
                "integration_instance": user_sync_source.integration_instance_id,
                "enabled": True,
                "description": "updated",
                "root_group_name": user_sync_source.root_group_name,
                "business_config": user_sync_source.business_config,
                "field_mapping": user_sync_source.field_mapping,
                "schedule_config": user_sync_source.schedule_config,
            },
            format="json",
        )

    assert response.status_code == 200
    user_sync_source.refresh_from_db()
    assert user_sync_source.description == "updated"
    mock_log.assert_called_once()


@pytest.mark.django_db
def test_department_options_requires_integration_instance(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.get("/api/v1/system_mgmt/user_sync_source/department_options/")

    assert response.status_code == 400


@pytest.mark.django_db
def test_root_group_name_available_reads_current_database(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/root_group_name_available/",
        {"root_group_name": user_sync_source.root_group_name},
    )

    assert response.status_code == 200
    assert response.data["available"] is False


@pytest.mark.django_db
def test_root_group_name_available_rejects_existing_root_group(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])
    Group.objects.create(name="Existing Root", parent_id=0)

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/root_group_name_available/",
        {"root_group_name": "Existing Root"},
    )

    assert response.status_code == 200
    assert response.data["available"] is False


@pytest.mark.django_db
def test_department_options_rejects_manual_input_provider(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.viewset.user_sync_source_viewset.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        response = api_client.get(
            "/api/v1/system_mgmt/user_sync_source/department_options/",
            {"integration_instance": ready_integration_instance.id},
        )

    assert response.status_code == 400
    assert "manual_input mode" in response.json()["message"]

@pytest.mark.django_db
def test_department_options_returns_serialized_errors_when_provider_call_fails(
    api_client, authenticated_user, ready_integration_instance
):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    failed_result = CapabilityExecutionResult.failed_result(
        "Feishu access token request failed",
        code="provider.request_failed",
        retryable=True,
    )

    with patch(
        "apps.system_mgmt.viewset.user_sync_source_viewset.RuntimeApplicationService.execute",
        return_value=failed_result,
    ):
        response = api_client.get(
            "/api/v1/system_mgmt/user_sync_source/department_options/",
            {
                "integration_instance": ready_integration_instance.id,
                "current_root_department_id": "",
                "department_id_type": "department_id",
            },
        )

    assert response.status_code == 400
    body = response.json()
    assert body["message"] == "Feishu access token request failed"
    assert body["errors"][0]["code"] == "provider.request_failed"


@pytest.mark.django_db
def test_department_options_returns_provider_tree_payload(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    result = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "dept-root",
            "items": [{"id": "dept-a", "name": "Dept A", "children": []}],
            "selected_id": "dept-a",
            "selection_missing": False,
        },
    )

    with patch(
        "apps.system_mgmt.viewset.user_sync_source_viewset.get_user_sync_root_department_input_mode",
        return_value="department_select",
    ), patch(
        "apps.system_mgmt.viewset.user_sync_source_viewset.RuntimeApplicationService.execute",
        return_value=result,
    ) as mock_execute:
        response = api_client.get(
            "/api/v1/system_mgmt/user_sync_source/department_options/",
            {"integration_instance": ready_integration_instance.id, "current_root_department_id": "dept-a"},
        )

    assert response.status_code == 200
    assert response.data["selected_id"] == "dept-a"
    assert response.data["items"][0]["id"] == "dept-a"
    assert mock_execute.called is True


@pytest.mark.django_db
def test_detail_records_returns_latest_runs(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    first_run = UserSyncRun.objects.create(source=user_sync_source, status="success")
    second_run = UserSyncRun.objects.create(source=user_sync_source, status="failed")

    response = api_client.get(f"/api/v1/system_mgmt/user_sync_source/{user_sync_source.id}/records/")

    assert response.status_code == 200
    returned_ids = {item["id"] for item in response.data}
    assert {first_run.id, second_run.id}.issubset(returned_ids)


@pytest.mark.django_db
def test_list_records_supports_search_by_source_name(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    source_a = UserSyncSource.objects.create(
        name="alpha-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Alpha Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={"mode": "disabled", "timezone": "Asia/Shanghai"},
    )
    source_b = UserSyncSource.objects.create(
        name="beta-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Beta Root",
        business_config={"root_department_id": "0"},
        field_mapping={},
        schedule_config={"mode": "disabled", "timezone": "Asia/Shanghai"},
    )
    UserSyncRun.objects.create(source=source_a, status="success", summary="alpha", started_at=timezone.now())
    UserSyncRun.objects.create(source=source_b, status="success", summary="beta", started_at=timezone.now())

    response = api_client.get(
        "/api/v1/system_mgmt/user_sync_source/records/",
        {"page": 1, "page_size": 10, "search": "alpha"},
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["source_name"] == "alpha-source"

@pytest.mark.django_db
def test_list_prefetches_only_latest_run_per_source(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    sources = [
        UserSyncSource.objects.create(
            name=f"source-list-{index}",
            integration_instance=ready_integration_instance,
            enabled=True,
            root_group_name=f"Root List {index}",
            business_config={"root_department_id": "0"},
            field_mapping={},
            schedule_config={},
        )
        for index in range(3)
    ]
    for source in sources:
        UserSyncRun.objects.create(source=source, status="failed", summary="old", started_at=timezone.now())
        UserSyncRun.objects.create(source=source, status="success", summary="latest", started_at=timezone.now())

    with CaptureQueriesContext(connection) as context:
        response = api_client.get("/api/v1/system_mgmt/user_sync_source/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    run_table = UserSyncRun._meta.db_table
    run_selects = [
        query["sql"]
        for query in context.captured_queries
        if query["sql"].lstrip().upper().startswith("SELECT") and run_table in query["sql"]
    ]
    assert len(run_selects) == 1
    assert {item["latest_run"]["summary"] for item in response.data["items"]} == {"latest"}


@pytest.mark.django_db
def test_preview_returns_not_found_for_unknown_source(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.post(
        "/api/v1/system_mgmt/user_sync_source/preview/",
        {"source_id": 999999},
        format="json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_preview_rejects_invalid_payload(api_client, authenticated_user, ready_integration_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ):
        response = api_client.post(
            "/api/v1/system_mgmt/user_sync_source/preview/",
            {
                "name": "preview-source",
                "integration_instance": ready_integration_instance.id,
                "enabled": True,
                "root_group_name": "",
                "business_config": {"root_department_id": "dept-root"},
                "field_mapping": {"username": "user_id"},
                "schedule_config": {},
            },
            format="json",
        )

    assert response.status_code == 400
    assert response.json()["result"] is False


@pytest.mark.django_db
def test_preview_uses_existing_source_without_persisting(api_client, authenticated_user, user_sync_source):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    preview_result = {"result": True, "message": "preview ok", "data": {"estimated_user_count": 3}}

    with patch(
        "apps.system_mgmt.serializers.user_sync_source_serializer.get_user_sync_root_department_input_mode",
        return_value="manual_input",
    ), patch("apps.system_mgmt.viewset.user_sync_source_viewset.preview_user_sync", return_value=preview_result) as mock_preview:
        response = api_client.post(
            "/api/v1/system_mgmt/user_sync_source/preview/",
            {
                "source_id": user_sync_source.id,
                "description": "preview only",
            },
            format="json",
        )

    assert response.status_code == 200
    assert response.json()["data"]["estimated_user_count"] == 3
    assert mock_preview.called is True
    user_sync_source.refresh_from_db()
    assert user_sync_source.description == ""


@pytest.mark.django_db
def test_sync_source_accepts_root_dn_without_base_dn_rail(
    api_client, authenticated_user, ready_ad_integration_instance
):
    """T3: AD user-sync source must accept business_config with only root_dn.

    The legacy is_sub_dn(root_dn, base_dn) boundary check used
    integration_instance.config.base_dn as a rail. With that field removed
    from the rail, a source specifying a root_dn that is not a sub of
    config.base_dn must still validate successfully — the rail is gone.
    """
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    # config.base_dn is intentionally a different DN than root_dn, so the
    # legacy is_sub_dn rail (before removal) raises ValidationError on it.
    ready_ad_integration_instance.config = {
        "host": "ldap.example.com",
        "port": 389,
        "bind_dn": "CN=svc,DC=boundary,DC=com",
        "base_dn": "DC=boundary,DC=com",
    }
    ready_ad_integration_instance.save(update_fields=["config"])

    response = api_client.post(
        "/api/v1/system_mgmt/user_sync_source/",
        {
            "name": "ad-source-no-rail",
            "integration_instance": ready_ad_integration_instance.id,
            "enabled": True,
            "root_group_name": "AD Root",
            "business_config": {"root_dn": "OU=A,DC=x,DC=y"},
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled", "timezone": "Asia/Shanghai"},
        },
        format="json",
    )

    assert response.status_code == 201, response.json()
    created = UserSyncSource.objects.get(name="ad-source-no-rail")
    assert created.business_config == {"root_dn": "OU=A,DC=x,DC=y"}


@pytest.mark.django_db
def test_sync_source_still_requires_root_dn_non_empty(
    api_client, authenticated_user, ready_ad_integration_instance
):
    """T3 complementary: empty root_dn must still be rejected for AD."""
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"user_sync-Add"}}
    authenticated_user.save(update_fields=["is_superuser"])

    response = api_client.post(
        "/api/v1/system_mgmt/user_sync_source/",
        {
            "name": "ad-source-empty-root",
            "integration_instance": ready_ad_integration_instance.id,
            "enabled": True,
            "root_group_name": "AD Empty Root",
            "business_config": {"root_dn": ""},
            "field_mapping": {"username": "sAMAccountName"},
            "schedule_config": {"mode": "disabled", "timezone": "Asia/Shanghai"},
        },
        format="json",
    )

    assert response.status_code == 400


PREVIEW_URL = "/api/v1/system_mgmt/user_sync_source/preview/"


@pytest.fixture
def password_init_preview_admin(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(username="preview_admin", password="pw", domain="domain.com", locale="en")
    admin.is_superuser = True
    admin.group_list = [{"id": 1, "name": "Default"}]
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def _password_init_preview_payload(integration_instance, **overrides):
    import uuid

    payload = {
        "name": overrides.pop("name", f"test-source-{uuid.uuid4().hex[:6]}"),
        "integration_instance": integration_instance.id,
        "root_group_name": overrides.pop("root_group_name", f"Feishu Root {uuid.uuid4().hex[:6]}"),
        "business_config": overrides.pop("business_config", {"root_department_id": "0"}),
        "schedule_config": overrides.pop("schedule_config", {"mode": "disabled"}),
        "field_mapping": overrides.pop("field_mapping", {"username": "user_id"}),
        "root_scope_field": overrides.pop("root_scope_field", "root_department_id"),
        "description": overrides.pop("description", ""),
        "enabled": overrides.pop("enabled", True),
    }
    payload.update(overrides)
    return payload


def _password_init_preview_result():
    return CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "all_department_id": "0",
            "items": [{"id": "dept-a", "parent_id": "0", "name": "Dept A"}],
            "user_list": [{"user_id": "ou_0", "name": "User 0", "email": "u0@b.c", "mobile": "", "department_ids": ["dept-a"]}],
        },
    )


@pytest.mark.django_db
def test_source_serializer_redacts_uniform_password(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="redacted-password-source",
        integration_instance=ready_integration_instance,
        root_group_name="Redacted Root",
        business_config={"root_department_id": "0"},
        platform_config={"password_init": {"mode": "uniform", "uniform_password": encrypt_for_vault("Str0ngP@ss!"), "email_channel_id": 7}},
    )

    password_init = UserSyncSourceSerializer(source).data["platform_config"]["password_init"]
    assert "uniform_password" not in password_init
    assert password_init["uniform_password_configured"] is True


@pytest.mark.django_db
def test_preview_rejects_missing_username_mapping(password_init_preview_admin, ready_integration_instance):
    response = password_init_preview_admin.post(
        PREVIEW_URL,
        _password_init_preview_payload(ready_integration_instance, field_mapping={}),
        format="json",
    )

    assert response.status_code == 400
    assert "username" in str(response.json()["errors"])


@pytest.mark.django_db
@patch.object(RuntimeApplicationService, "execute", return_value=_password_init_preview_result())
@pytest.mark.parametrize(
    ("config_key", "password_init", "status"),
    [
        ("business_config", {"mode": "random", "email_channel_id": 7}, 400),
        ("platform_config", {"mode": "random", "email_channel_id": 7}, 200),
        ("platform_config", {"mode": "none"}, 200),
        ("business_config", {"mode": "none"}, 400),
    ],
)
def test_preview_keeps_password_init_in_platform_config(
    mock_execute, config_key, password_init, status, password_init_preview_admin, ready_integration_instance
):
    if config_key == "business_config":
        payload = _password_init_preview_payload(
            ready_integration_instance,
            business_config={"root_department_id": "0", "password_init": password_init},
        )
    else:
        payload = _password_init_preview_payload(
            ready_integration_instance,
            platform_config={"password_init": password_init},
        )

    response = password_init_preview_admin.post(PREVIEW_URL, payload, format="json")
    assert response.status_code == status, response.content
    if status == 400:
        assert "password_init" in str(response.json())
    else:
        assert response.json()["result"] is True


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("password_init", "expected_error"),
    [
        ({"mode": "typo"}, "Unsupported password_init mode"),
        ({"mode": "random"}, "email_channel_id is required"),
        ({"mode": "uniform", "uniform_password": "Abc12345!"}, "email_channel_id is required"),
        ({"mode": "uniform", "email_channel_id": 7}, "uniform_password is required"),
        ({"mode": "uniform", "uniform_password": "123", "email_channel_id": 7}, "密码"),
    ],
)
def test_preview_rejects_invalid_platform_password_init(
    password_init, expected_error, password_init_preview_admin, ready_integration_instance
):
    response = password_init_preview_admin.post(
        PREVIEW_URL,
        _password_init_preview_payload(ready_integration_instance, platform_config={"password_init": password_init}),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["result"] is False
    assert expected_error in str(response.json())


# ---------------------------------------------------------------------------
# Task 3.7-3.8: run_detail endpoint
# ---------------------------------------------------------------------------


RUN_DETAIL_URL = "/api/v1/system_mgmt/user_sync_source/runs/{run_id}/"


@pytest.mark.django_db
def test_run_detail_returns_full_run_payload(api_client, authenticated_user, user_sync_source):
    """正常路径:GET /runs/{id}/ 返回 UserSyncRunSerializer 完整数据(含 payload)。"""
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    run = UserSyncRun.objects.create(
        source=user_sync_source,
        trigger_mode="manual",
        status="success",
        summary="ok",
        payload={
            "password_init_mode": "none",
            "phase_progress": {
                "fetch_directory": {"current": 12, "total": 12, "status": "finish"},
                "sync_users": {"current": 5, "total": 5, "status": "finish"},
            },
        },
    )

    api_client.force_login(authenticated_user)
    response = api_client.get(RUN_DETAIL_URL.format(run_id=run.id))

    assert response.status_code == 200
    data = response.json()
    # UserSyncRunSerializer fields=__all__ 输出包含 id / status / payload 等
    # 部分字段可能被项目基类包装(见 BaseUser / MaintainerViewSet)
    if "data" in data and isinstance(data["data"], dict):
        data = data["data"]
    assert data.get("id") == run.id
    assert data.get("status") == "success"
    assert data.get("source_name") == user_sync_source.name
    payload = data.get("payload", {})
    assert payload.get("password_init_mode") == "none"
    assert "phase_progress" in payload
    assert payload["phase_progress"]["fetch_directory"]["status"] == "finish"


@pytest.mark.django_db
def test_run_detail_returns_404_for_missing_run(api_client, authenticated_user):
    """run_id 不存在返回 404。"""
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"user_sync-View"}}
    api_client.cookies["current_team"] = "1"

    api_client.force_login(authenticated_user)
    response = api_client.get(RUN_DETAIL_URL.format(run_id=99999999))
    assert response.status_code == 404
    assert response.json()["result"] is False
    assert "Run not found" in response.json()["message"]


@pytest.mark.django_db
def test_run_detail_returns_403_for_invisible_source(api_client, ready_integration_instance):
    """用户对 source 无 user_sync-View 权限时,返回 403 或 404(被可见性过滤)。"""
    from apps.base.models import User as BaseUser
    from apps.system_mgmt.models import UserSyncRun

    source = UserSyncSource.objects.create(
        name="invisible-source",
        integration_instance=ready_integration_instance,
        enabled=True,
        root_group_name="Invisible",
        business_config={"root_department_id": "0"},
        field_mapping={"username": "user_id"},
        schedule_config={"mode": "disabled"},
    )
    run = UserSyncRun.objects.create(source=source, trigger_mode="manual", status="success", summary="ok")

    # 无任何权限的非超管 base 用户(与 authenticated_user 同模型)
    no_perm_user = BaseUser.objects.create_user(
        username="no-perm-user-run",
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[],
        roles=[],
        is_superuser=False,
    )
    no_perm_user.permission = {}  # 进程内属性,middleware 用
    api_client.cookies["current_team"] = "1"

    api_client.force_login(no_perm_user)
    response = api_client.get(RUN_DETAIL_URL.format(run_id=run.id))
    # 403(权限不足)或 404(被 get_queryset_by_permission 过滤)都是合规行为
    assert response.status_code in (403, 404)

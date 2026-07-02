from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.system_mgmt.models import Group, IntegrationInstance, User, UserSyncRun, UserSyncSource
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.user_sync_service import delete_user_sync_source


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
                "field_mapping": {},
                "schedule_config": {},
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
                "field_mapping": {},
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
                "field_mapping": {},
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
                "field_mapping": {},
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
            "field_mapping": {},
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
            "field_mapping": {},
            "schedule_config": {"mode": "disabled", "timezone": "Asia/Shanghai"},
        },
        format="json",
    )

    assert response.status_code == 400

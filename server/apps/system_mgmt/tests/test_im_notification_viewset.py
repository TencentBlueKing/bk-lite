from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.response import Response

from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping, IntegrationInstance, User
from apps.system_mgmt.serializers.im_notification_channel_serializer import IMNotificationChannelSerializer, IMNotificationSyncRunSerializer
from apps.system_mgmt.viewset.im_notification_channel_viewset import IMNotificationChannelViewSet


@pytest.fixture
def ready_im_instance(db):
    return IntegrationInstance.objects.create(
        name="feishu-im",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready", "login_auth": "pending_verification", "user_sync": "pending_verification"},
        config={"app_id": "cli_xxx", "app_secret": "plain-secret"},
    )


@pytest.fixture
def channel(ready_im_instance):
    return IMNotificationChannel.objects.create(
        name="feishu-im",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[],
    )


@pytest.mark.django_db
def test_channel_rejects_external_match_field_not_declared_by_manifest(ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        data={
            "name": "feishu-im",
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "status": "pending_sync",
            "platform_match_field": "email",
            "external_match_field": "name",
            "external_receive_field": "user_id",
            "team": [],
        }
    )

    assert serializer.is_valid() is False
    assert "external_match_field" in serializer.errors


@pytest.mark.django_db
def test_channel_rejects_unknown_status(ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        data={
            "name": "invalid-status-channel",
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "status": "mystery",
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "team": [],
        }
    )

    assert serializer.is_valid() is False
    assert "status" in serializer.errors


@pytest.mark.django_db
def test_sync_run_rejects_unknown_status(channel):
    serializer = IMNotificationSyncRunSerializer(
        data={
            "channel": channel.id,
            "trigger_mode": "manual",
            "status": "mystery",
            "summary": "started",
        }
    )

    assert serializer.is_valid() is False
    assert "status" in serializer.errors


@pytest.mark.django_db
def test_channel_update_marks_needs_resync_when_critical_config_changes(channel, ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        instance=channel,
        data={
            "name": channel.name,
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "description": channel.description,
            "platform_match_field": "username",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "team": [],
        },
    )

    assert serializer.is_valid(), serializer.errors
    updated_channel = serializer.save()

    assert updated_channel.status == "needs_resync"


@pytest.mark.django_db
def test_channel_create_syncs_periodic_task_when_schedule_enabled(ready_im_instance):
    with patch("apps.system_mgmt.models.im_notification_channel.IMNotificationChannel.create_sync_periodic_task") as mock_sync:
        serializer = IMNotificationChannelSerializer(
            data={
                "name": "scheduled-channel",
                "integration_instance": ready_im_instance.id,
                "enabled": True,
                "description": "",
                "platform_match_field": "email",
                "external_match_field": "email",
                "external_receive_field": "user_id",
                "schedule_config": {"enabled": True, "sync_time": "02:00"},
                "team": [],
            },
        )
        assert serializer.is_valid(), serializer.errors

        instance = serializer.save()

    assert instance.schedule_config == {"enabled": True, "sync_time": "02:00"}
    mock_sync.assert_called_once_with()


@pytest.mark.django_db
def test_channel_rejects_invalid_schedule_sync_time(ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        data={
            "name": "scheduled-channel",
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "description": "",
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "schedule_config": {"enabled": True, "sync_time": "25:00"},
            "team": [],
        },
    )

    assert serializer.is_valid() is False
    assert "schedule_config" in serializer.errors


@pytest.mark.django_db
def test_channel_update_syncs_periodic_task_when_schedule_enabled(channel, ready_im_instance):
    with patch("apps.system_mgmt.models.im_notification_channel.IMNotificationChannel.create_sync_periodic_task") as mock_sync:
        serializer = IMNotificationChannelSerializer(
            instance=channel,
            data={
                "name": channel.name,
                "integration_instance": ready_im_instance.id,
                "enabled": True,
                "description": channel.description,
                "platform_match_field": "email",
                "external_match_field": "email",
                "external_receive_field": "user_id",
                "schedule_config": {"enabled": True, "sync_time": "02:00"},
                "team": [],
            },
        )
        assert serializer.is_valid(), serializer.errors

        instance = serializer.save()

    assert instance.schedule_config == {"enabled": True, "sync_time": "02:00"}
    mock_sync.assert_called_once_with()


@pytest.mark.django_db
def test_sync_mappings_enqueues_run_and_returns_run_id(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.im_notification_channel_viewset.execute_im_notification_sync_run_task.delay") as mock_delay:
        response = api_client.post(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/sync_mappings/")

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert "run_id" in response.json()["data"]
    mock_delay.assert_called_once_with(response.json()["data"]["run_id"])


@pytest.mark.django_db
def test_channel_serializer_returns_display_status_and_display_sync_status(channel):
    IMNotificationSyncRun.objects.create(
        channel=channel,
        status="running",
        summary="syncing",
        started_at=timezone.now(),
        locked_config_snapshot={},
    )

    data = IMNotificationChannelSerializer(channel).data

    assert data["display_status"] == "syncing"
    assert data["display_sync_status"] == "running"
    assert data["display_sync_summary"] == "syncing"
    assert data["latest_sync_status"] == "running"
    assert data["status"] == "pending_sync"


@pytest.mark.django_db
def test_channel_serializer_returns_never_synced_when_no_run(channel):
    data = IMNotificationChannelSerializer(channel).data
    assert data["display_sync_status"] == "never_synced"
    assert data["display_sync_summary"] == ""


@pytest.mark.django_db
def test_channel_serializer_returns_partial_when_latest_run_partial(channel):
    IMNotificationSyncRun.objects.create(
        channel=channel,
        status="partial",
        summary="Matched 5 of 10 external users",
        started_at=timezone.now(),
        locked_config_snapshot={},
    )
    data = IMNotificationChannelSerializer(channel).data
    assert data["display_sync_status"] == "partial"
    assert data["display_sync_summary"] == "Matched 5 of 10 external users"


@pytest.mark.django_db
def test_records_returns_channel_runs_only(api_client, authenticated_user, channel, ready_im_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    other_channel = IMNotificationChannel.objects.create(
        name="other-channel",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[],
    )

    newer = IMNotificationSyncRun.objects.create(channel=channel, status="running", summary="newer", started_at=timezone.now(), locked_config_snapshot={})
    IMNotificationSyncRun.objects.create(channel=other_channel, status="failed", summary="other", started_at=timezone.now(), locked_config_snapshot={})

    response = api_client.get(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/records/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["id"] == newer.id


@pytest.mark.django_db
def test_list_prefetches_only_latest_sync_run_per_channel(api_client, authenticated_user, ready_im_instance):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    channels = [
        IMNotificationChannel.objects.create(
            name=f"channel-list-{index}",
            integration_instance=ready_im_instance,
            enabled=True,
            status="pending_sync",
            platform_match_field="email",
            external_match_field="email",
            external_receive_field="user_id",
            team=[],
        )
        for index in range(3)
    ]
    for channel_item in channels:
        IMNotificationSyncRun.objects.create(
            channel=channel_item,
            status="failed",
            summary="old",
            started_at=timezone.now(),
            locked_config_snapshot={},
        )
        IMNotificationSyncRun.objects.create(
            channel=channel_item,
            status="success",
            summary="latest",
            started_at=timezone.now(),
            locked_config_snapshot={},
        )

    with CaptureQueriesContext(connection) as context:
        response = api_client.get("/api/v1/system_mgmt/im_notification_channel/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    run_table = IMNotificationSyncRun._meta.db_table
    run_selects = [
        query["sql"]
        for query in context.captured_queries
        if query["sql"].lstrip().upper().startswith("SELECT") and run_table in query["sql"]
    ]
    assert len(run_selects) == 1
    assert {item["latest_sync_summary"] for item in response.data["items"]} == {"latest"}


@pytest.mark.django_db
def test_destroy_channel_deletes_periodic_task(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.im_notification_channel_viewset.IMNotificationChannel.delete_sync_periodic_task") as mock_delete:
        response = api_client.delete(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/")

    assert response.status_code == 200
    mock_delete.assert_called_once_with()


@pytest.mark.django_db
def test_destroy_channel_logs_operation_when_destroy_returns_204(authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])
    request = MagicMock()
    request.user = authenticated_user
    viewset = IMNotificationChannelViewSet()
    viewset.get_object = MagicMock(return_value=channel)

    with patch(
        "apps.system_mgmt.viewset.im_notification_channel_viewset.MaintainerViewSet.destroy",
        return_value=Response(status=204),
    ), patch(
        "apps.system_mgmt.viewset.im_notification_channel_viewset.IMNotificationChannel.delete_sync_periodic_task"
    ), patch("apps.system_mgmt.viewset.im_notification_channel_viewset.log_operation") as mock_log:
        response = IMNotificationChannelViewSet.destroy.__wrapped__(viewset, request)

    assert response.status_code == 204
    mock_log.assert_called_once()


@pytest.mark.django_db
def test_list_filters_channels_by_team(api_client, authenticated_user, ready_im_instance):
    authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
    authenticated_user.save(update_fields=["group_list"])
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}

    IMNotificationChannel.objects.create(
        name="visible-channel",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[1],
    )
    IMNotificationChannel.objects.create(
        name="hidden-channel",
        integration_instance=ready_im_instance,
        enabled=True,
        status="pending_sync",
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        team=[2],
    )

    response = api_client.get("/api/v1/system_mgmt/im_notification_channel/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    names = {item["name"] for item in response.data["items"]}
    assert "visible-channel" in names
    assert "hidden-channel" not in names


@pytest.mark.django_db
def test_retrieve_rejects_channel_outside_user_team(api_client, authenticated_user, channel):
    authenticated_user.group_list = [{"id": 999, "name": "Other Team"}]
    authenticated_user.save(update_fields=["group_list"])
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}

    response = api_client.get(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/")

    assert response.status_code == 403


@pytest.mark.django_db
def test_create_rejects_team_outside_user_scope(api_client, authenticated_user, ready_im_instance):
    authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
    authenticated_user.save(update_fields=["group_list"])
    authenticated_user.permission = {"system-manager": {"channel_list-Add"}}

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/",
        {
            "name": "scoped-channel",
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "team": [99],
        },
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_update_rejects_team_outside_user_scope(api_client, authenticated_user, channel, ready_im_instance):
    authenticated_user.group_list = [{"id": 1, "name": "Team A"}]
    authenticated_user.save(update_fields=["group_list"])
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}

    response = api_client.put(
        f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/",
        {
            "name": channel.name,
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "team": [99],
        },
    )

    assert response.status_code == 403


@pytest.mark.django_db
@patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService")
def test_send_action_dispatches_to_provider(mock_runtime_class, api_client, authenticated_user, channel, ready_im_instance):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}

    channel.status = "ready"
    channel.save(update_fields=["status"])

    user = User.objects.create(
        username="receiver",
        display_name="Receiver",
        email="receiver@example.com",
        domain="domain.com",
    )
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="user_id",
        external_identity_value="u123",
        external_receive_key="user_id",
        external_snapshot={"user_id": "u123"},
    )

    mock_runtime = mock_runtime_class.return_value
    mock_runtime.execute.return_value = MagicMock(success=True, summary="sent", to_dict=lambda: {"ok": True})

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": channel.id, "user_ids": [user.id], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 200
    assert response.json()["result"] is True


@pytest.mark.django_db
def test_send_action_rejects_channel_not_ready(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": channel.id, "user_ids": [], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 400
    assert "requires a successful sync" in response.json()["message"]


@pytest.mark.django_db
def test_mappings_returns_channel_user_mappings(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-View"}}
    authenticated_user.save(update_fields=["is_superuser"])

    user = User.objects.create(
        username="mapped-user",
        display_name="Mapped User",
        email="mapped@example.com",
        domain="domain.com",
    )
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="user_id",
        external_identity_value="ou_123",
        external_receive_key="user_id",
        external_snapshot={"user_id": "ou_123"},
    )

    response = api_client.get(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/mappings/", {"page": 1, "page_size": 10})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["username"] == "mapped-user"


@pytest.mark.django_db
def test_test_send_uses_default_receiver_when_receivers_missing(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.im_notification_channel_viewset.send_im_notification", return_value={"result": True, "message": "ok"}) as mock_send:
        response = api_client.post(
            f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/test_send/",
            {"title": "Ping", "content": "Body"},
            format="json",
        )

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert mock_send.call_args.kwargs["receivers"] == [authenticated_user.id]


@pytest.mark.django_db
def test_test_send_returns_error_payload(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch(
        "apps.system_mgmt.viewset.im_notification_channel_viewset.send_im_notification",
        return_value={"result": False, "message": "failed"},
    ):
        response = api_client.post(
            f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/test_send/",
            {"title": "Ping", "content": "Body", "receivers": ["tester"]},
            format="json",
        )

    assert response.status_code == 400
    assert response.json()["message"] == "failed"


@pytest.mark.django_db
def test_send_action_rejects_invalid_channel_or_user_ids(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": "bad", "user_ids": ["oops"], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid channel_id or user_ids"


@pytest.mark.django_db
def test_send_action_rejects_missing_channel(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    authenticated_user.permission = {"system-manager": {"channel_list-Edit"}}

    response = api_client.post(
        "/api/v1/system_mgmt/im_notification_channel/send/",
        {"channel_id": 999999, "user_ids": [1], "title": "Hello", "content": "World"},
    )

    assert response.status_code == 404
    assert response.json()["message"] == "IM notification channel not found"

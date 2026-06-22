from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IntegrationInstance
from apps.system_mgmt.serializers.im_notification_channel_serializer import IMNotificationChannelSerializer


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
def test_channel_serializer_returns_display_status_from_channel_and_latest_run(channel):
    IMNotificationSyncRun.objects.create(
        channel=channel,
        status="running",
        summary="syncing",
        started_at=timezone.now(),
        locked_config_snapshot={},
    )

    data = IMNotificationChannelSerializer(channel).data

    assert data["display_status"] == "syncing"
    assert data["latest_sync_status"] == "running"
    assert data["status"] == "pending_sync"


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
def test_destroy_channel_deletes_periodic_task(api_client, authenticated_user, channel):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"channel_list-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])

    with patch("apps.system_mgmt.viewset.im_notification_channel_viewset.IMNotificationChannel.delete_sync_periodic_task") as mock_delete:
        response = api_client.delete(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/")

    assert response.status_code == 200
    mock_delete.assert_called_once_with()

import json
from unittest.mock import patch

import pytest

from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping, IntegrationInstance, User
from apps.system_mgmt.providers.adapters.feishu import FeishuIMNotificationAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.im_notification_service import (
    CHANNEL_STATUS_NEEDS_RESYNC,
    CHANNEL_STATUS_READY,
    SYNC_RUN_STATUS_PARTIAL,
    create_im_notification_sync_run,
    critical_config_changed,
    execute_im_notification_sync_run,
    send_im_notification,
)


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


@pytest.fixture
def user(db):
    return User.objects.create(
        username="tester",
        display_name="Tester",
        email="tester@example.com",
        password="",
        domain="domain.com",
    )


@pytest.mark.django_db
def test_im_notification_mapping_stores_identity_and_snapshot_only(channel, user):
    mapping = IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="user_id",
        external_identity_value="ou_123",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={"platform_field": "email", "external_field": "email"},
        external_snapshot={"user_id": "ou_123", "email": "tester@example.com"},
    )

    assert mapping.external_identity_value == "ou_123"
    assert mapping.external_receive_key == "user_id"
    assert "user_id" in mapping.external_snapshot


@pytest.mark.django_db
def test_execute_im_notification_sync_run_marks_partial_when_some_external_users_unmatched(channel, user):
    run = IMNotificationSyncRun.objects.create(
        channel=channel,
        status="running",
        summary="started",
        locked_config_snapshot={
            "integration_instance_id": channel.integration_instance_id,
            "provider_key": channel.integration_instance.provider_key,
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
        },
    )
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "external_users": [
                {"user_id": "ou_123", "email": "tester@example.com", "name": "Tester"},
                {"user_id": "ou_404", "email": "missing@example.com", "name": "Missing"},
            ]
        },
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_im_notification_sync_run(run.id)

    run.refresh_from_db()
    channel.refresh_from_db()
    mapping = IMNotificationUserMapping.objects.get(channel=channel, user=user)

    assert result["result"] is True
    assert run.status == SYNC_RUN_STATUS_PARTIAL
    assert IMNotificationUserMapping.objects.filter(channel=channel).count() == 1
    assert run.unmatched_count == 1
    assert mapping.external_identity_value == "ou_123"
    assert channel.status == CHANNEL_STATUS_READY


@pytest.mark.django_db
def test_send_im_notification_is_blocked_when_channel_needs_resync(channel, user):
    channel.status = CHANNEL_STATUS_NEEDS_RESYNC
    channel.save(update_fields=["status"])

    result = send_im_notification(channel.id, "Title", "Body", [user.id])

    assert result["result"] is False
    assert "requires a successful sync" in result["message"]


@pytest.mark.django_db
def test_send_im_notification_reads_receive_id_from_snapshot(channel, user):
    channel.status = CHANNEL_STATUS_READY
    channel.save(update_fields=["status"])
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="open_id",
        external_identity_value="ou_identity",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={},
        external_snapshot={"user_id": "ou_123", "open_id": "ou_identity"},
    )
    payload = CapabilityExecutionResult.success_result("sent", payload={"sent_count": 1})

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload) as mock_execute:
        result = send_im_notification(channel.id, "Title", "Body", [user.id])

    assert result["result"] is True
    assert mock_execute.call_args.kwargs["receive_ids"] == ["ou_123"]
    assert mock_execute.call_args.kwargs["receive_id_type"] == "user_id"


def test_channel_update_marks_needs_resync_when_critical_config_changes(channel, ready_im_instance):
    changed = critical_config_changed(
        channel,
        {
            "integration_instance": ready_im_instance,
            "platform_match_field": "username",
            "external_match_field": "email",
            "external_receive_field": "user_id",
        },
    )

    assert changed is True


def test_feishu_send_message_serializes_multiline_text_content():
    channel = IMNotificationChannel(external_receive_field="user_id")
    expected_content = json.dumps({"text": "Title\nBody"}, ensure_ascii=False)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"code": 0}

    with patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=FakeResponse()) as mock_post:
        result = FeishuIMNotificationAdapter.send_message(
            config={},
            provider_key="feishu",
            capability_key="im_notification",
            title="Title",
            content="Body",
            receive_id_type="user_id",
            receive_ids=["ou_123"],
        )

    assert result.success is True
    assert mock_post.call_args.kwargs["json"]["content"] == expected_content


@pytest.mark.django_db
def test_create_im_notification_sync_run_persists_locked_snapshot(channel):
    result = create_im_notification_sync_run(channel.id)

    assert result["result"] is True
    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])
    assert run.locked_config_snapshot["platform_match_field"] == "email"
    assert run.locked_config_snapshot["external_match_field"] == "email"
    assert run.locked_config_snapshot["external_receive_field"] == "user_id"


@pytest.mark.django_db
def test_im_notification_channel_stores_schedule_config_and_run_trigger_mode(channel):
    channel.schedule_config = {"enabled": True, "sync_time": "02:00"}
    channel.save(update_fields=["schedule_config"])

    run = IMNotificationSyncRun.objects.create(
        channel=channel,
        trigger_mode="schedule",
        status="running",
    )

    channel.refresh_from_db()
    assert channel.schedule_config["enabled"] is True
    assert channel.schedule_config["sync_time"] == "02:00"
    assert run.trigger_mode == "schedule"


@pytest.mark.django_db
def test_create_im_notification_sync_run_accepts_trigger_mode(channel):
    result = create_im_notification_sync_run(channel.id, trigger_mode="schedule")

    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])
    assert run.trigger_mode == "schedule"


@pytest.mark.django_db
def test_schedule_trigger_skips_when_run_is_already_running(channel):
    IMNotificationSyncRun.objects.create(channel=channel, trigger_mode="manual", status="running")

    result = create_im_notification_sync_run(channel.id, trigger_mode="schedule")

    assert result["result"] is False


@pytest.mark.django_db
def test_schedule_im_notification_sync_enqueues_existing_run_executor(channel):
    from apps.system_mgmt.tasks import schedule_im_notification_sync

    with patch("apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay") as mock_delay:
        result = schedule_im_notification_sync(channel.id)

    assert result["result"] is True
    mock_delay.assert_called_once()


@pytest.mark.django_db
def test_pending_sync_channel_completes_first_sync_through_schedule_path(channel, user):
    from apps.system_mgmt.tasks import schedule_im_notification_sync

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_users": [{"user_id": "ou_123", "email": "tester@example.com", "name": "Tester"}]},
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        with patch("apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay") as mock_delay:
            def run_immediately(run_id):
                return execute_im_notification_sync_run(run_id)

            mock_delay.side_effect = run_immediately
            result = schedule_im_notification_sync(channel.id)

    channel.refresh_from_db()
    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])

    assert result["result"] is True
    assert run.trigger_mode == "schedule"
    assert run.status == "success"
    assert channel.status == CHANNEL_STATUS_READY

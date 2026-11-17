import json
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.system_mgmt.models import (
    IMAccountAssociation,
    IMNotificationChannel,
    IMNotificationSyncRun,
    IMNotificationUserMapping,
    IntegrationInstance,
    User,
)
from apps.system_mgmt.providers.builtin.feishu.adapters.im_notification import FeishuIMNotificationAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.im_notification_service import (
    CHANNEL_STATUS_READY,
    EXTERNAL_CALL_FAILED,
    EXTERNAL_SEND_FAILED,
    EXTERNAL_SEND_SUCCEEDED,
    SYNC_RUN_STATUS_PARTIAL,
    association_config_changed,
    create_account_association_sync_run,
    execute_im_notification_sync_run,
    send_im_notification,
)

_LOG_FORMATTER = logging.Formatter("%(levelname)s %(name)s %(message)s")
_SUMMARY_SENTINEL = "secret-sentinel-SUMMARY"
_PAYLOAD_SENTINEL = "secret-sentinel-PAYLOAD"


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
    association = IMAccountAssociation.objects.create(
        name="feishu-association",
        integration_instance=ready_im_instance,
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        status="ready",
    )
    return IMNotificationChannel.objects.create(
        name="feishu-im",
        integration_instance=ready_im_instance,
        account_association=association,
        enabled=True,
        status="ready",
        team=[],
    )


@pytest.fixture
def user(db):
    return User.objects.create(
        user_id=str(uuid.uuid4()),
        username="tester",
        display_name="Tester",
        email="tester@example.com",
        password="",
        domain="domain.com",
    )


@pytest.mark.django_db
def test_im_notification_mapping_stores_identity_and_snapshot_only(channel, user):
    mapping = IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
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
        account_association=channel.account_association,
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
    mapping = IMNotificationUserMapping.objects.get(account_association=channel.account_association, user=user)

    assert result["result"] is True
    assert run.status == SYNC_RUN_STATUS_PARTIAL
    assert IMNotificationUserMapping.objects.filter(account_association=channel.account_association).count() == 1
    assert run.unmatched_count == 1
    assert mapping.external_identity_value == "ou_123"
    assert channel.status == CHANNEL_STATUS_READY


def test_completed_sync_run_status_requires_a_match_for_partial():
    from apps.system_mgmt.services.im_notification_service import _completed_sync_run_status

    assert _completed_sync_run_status(3, 0, 0) == "success"
    assert _completed_sync_run_status(1, 2, 0) == "partial"
    assert _completed_sync_run_status(1, 0, 1) == "partial"
    assert _completed_sync_run_status(0, 3, 0) == "failed"
    assert _completed_sync_run_status(0, 0, 1) == "failed"
    assert _completed_sync_run_status(0, 0, 0) == "success"


@pytest.mark.django_db
def test_execute_im_notification_sync_run_marks_failed_when_nobody_matches(channel, user):
    IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
        user=user,
        external_identity_key="user_id",
        external_identity_value="old-keep",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={},
        external_snapshot={"user_id": "old-keep"},
    )
    run = IMNotificationSyncRun.objects.create(
        account_association=channel.account_association,
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
                {"user_id": "ou_1", "email": "missing-1@example.com", "name": "One"},
                {"user_id": "ou_2", "email": "missing-2@example.com", "name": "Two"},
                {"user_id": "ou_3", "email": "missing-3@example.com", "name": "Three"},
            ]
        },
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        result = execute_im_notification_sync_run(run.id)

    run.refresh_from_db()
    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    assert result["result"] is True
    assert run.status == "failed"
    assert run.matched_count == 0
    assert run.unmatched_count == 3
    assert run.conflict_count == 0
    assert channel.account_association.status == "needs_resync"
    assert channel.status == "needs_resync"
    assert not IMNotificationUserMapping.objects.filter(account_association=channel.account_association).exists()


@pytest.mark.django_db
def test_execute_im_notification_sync_run_stores_bounded_redacted_diagnostics(channel, user):
    run = IMNotificationSyncRun.objects.create(
        account_association=channel.account_association,
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
                {
                    "user_id": "ou_123",
                    "open_id": "open_123",
                    "email": "tester@example.com",
                    "mobile": "13800000000",
                    "name": "Tester",
                    "password": "should-not-persist",
                    "raw_profile": {"large": "payload"},
                },
                {
                    "user_id": "ou_404",
                    "email": "missing@example.com",
                    "name": "Missing",
                    "access_token": "token-should-not-persist",
                },
            ],
            "provider_secret": "should-not-persist",
        },
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        execute_im_notification_sync_run(run.id)

    run.refresh_from_db()
    mapping = IMNotificationUserMapping.objects.get(account_association=channel.account_association, user=user)

    assert "external_users" not in run.payload.get("payload", {})
    assert "provider_secret" not in run.payload.get("payload", {})
    assert "password" not in mapping.external_snapshot
    assert "raw_profile" not in mapping.external_snapshot
    assert mapping.external_snapshot == {
        "user_id": "ou_123",
        "open_id": "open_123",
        "email": "tester@example.com",
        "mobile": "13800000000",
        "name": "Tester",
    }
    assert "access_token" not in str(run.payload["unmatched_issues"])


@pytest.mark.django_db
def test_send_im_notification_is_blocked_when_association_has_no_usable_result(channel, user):
    channel.account_association.status = "needs_resync"
    channel.account_association.save(update_fields=["status"])

    result = send_im_notification(channel.id, "Title", "Body", [user.id])

    assert result["result"] is False
    assert result["message"] == "IM account association has no usable result"


@pytest.mark.django_db
def test_im_notification_sync_and_send_are_blocked_when_capability_is_disabled(channel, user):
    channel.integration_instance.capability_enabled = {"im_notification": False}
    channel.integration_instance.save(update_fields=["capability_enabled"])
    channel.status = CHANNEL_STATUS_READY
    channel.save(update_fields=["status"])

    sync_result = create_account_association_sync_run(channel.account_association_id)
    send_result = send_im_notification(channel.id, "Title", "Body", [user.id])

    assert sync_result == {"result": False, "message": "IM notification capability is not ready"}
    assert send_result == {"result": False, "message": "IM notification channel is not ready"}


@pytest.mark.django_db
def test_send_im_notification_reads_receive_id_from_snapshot(channel, user):
    channel.status = CHANNEL_STATUS_READY
    channel.save(update_fields=["status"])
    IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
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


def test_association_update_marks_needs_resync_when_match_field_changes(channel):
    changed = association_config_changed(
        channel.account_association,
        {
            "platform_match_field": "username",
            "external_match_field": "email",
            "external_receive_field": "user_id",
        },
    )

    assert changed is True


def test_feishu_send_message_serializes_multiline_text_content():
    expected_content = json.dumps({"text": "Title\nBody"}, ensure_ascii=False)

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"code": 0}

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.im_notification._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), patch("apps.system_mgmt.providers.builtin.feishu.adapters.im_notification.requests.post", return_value=FakeResponse()) as mock_post:
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
def test_create_account_association_sync_run_persists_locked_snapshot(channel):
    result = create_account_association_sync_run(channel.account_association_id)

    assert result["result"] is True
    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])
    assert run.locked_config_snapshot["platform_match_field"] == "email"
    assert run.locked_config_snapshot["external_match_field"] == "email"
    assert run.locked_config_snapshot["external_receive_field"] == "user_id"
    assert run.locked_config_snapshot["identity"] == {"app_id": "cli_xxx"}


@pytest.mark.django_db
def test_account_association_stores_schedule_config_and_run_trigger_mode(channel):
    channel.account_association.schedule_config = {"enabled": True, "sync_time": "02:00"}
    channel.account_association.save(update_fields=["schedule_config"])

    run = IMNotificationSyncRun.objects.create(
        account_association=channel.account_association,
        trigger_mode="schedule",
        status="running",
    )

    channel.account_association.refresh_from_db()
    assert channel.account_association.schedule_config["enabled"] is True
    assert channel.account_association.schedule_config["sync_time"] == "02:00"
    assert run.trigger_mode == "schedule"


@pytest.mark.django_db
def test_create_im_notification_sync_run_accepts_trigger_mode(channel):
    result = create_account_association_sync_run(channel.account_association_id, trigger_mode="schedule")

    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])
    assert run.trigger_mode == "schedule"


@pytest.mark.django_db
def test_schedule_trigger_skips_when_run_is_already_running(channel):
    IMNotificationSyncRun.objects.create(account_association=channel.account_association, trigger_mode="manual", status="running")

    result = create_account_association_sync_run(channel.account_association_id, trigger_mode="schedule")

    assert result["result"] is False


@pytest.mark.django_db
def test_im_notification_sync_run_allows_only_one_running_run_per_channel(channel):
    IMNotificationSyncRun.objects.create(account_association=channel.account_association, trigger_mode="manual", status="running")

    with pytest.raises(IntegrityError):
        IMNotificationSyncRun.objects.create(account_association=channel.account_association, trigger_mode="schedule", status="running")


@pytest.mark.django_db
def test_mysql_guard_migration_rejects_duplicate_im_run_without_changing_status(channel):
    from importlib import import_module

    from django.apps import apps
    from django.db import connection, models

    if connection.vendor != "mysql":
        pytest.skip("MySQL 5.7 legacy data migration contract")

    older = IMNotificationSyncRun.objects.create(account_association=channel.account_association, status="running")
    with pytest.raises(IntegrityError), transaction.atomic():
        IMNotificationSyncRun.objects.bulk_create([IMNotificationSyncRun(account_association=channel.account_association, status="running")])
    newer = IMNotificationSyncRun.objects.create(account_association=channel.account_association, status="failed")
    models.QuerySet(model=IMNotificationSyncRun, using="default").filter(pk=newer.pk).update(
        status="running",
        running_guard=None,
    )

    migration = import_module("apps.system_mgmt.migrations.0045_cross_database_running_guards")
    schema_editor = SimpleNamespace(connection=connection)
    with pytest.raises(RuntimeError, match="重复运行记录"):
        migration.ensure_running_runs_unique(apps, schema_editor)

    older.refresh_from_db()
    newer.refresh_from_db()
    assert older.status == "running"
    assert older.running_guard is True
    assert newer.status == "running"
    assert newer.running_guard is None


@pytest.mark.django_db
def test_schedule_account_association_sync_enqueues_existing_run_executor(channel):
    from apps.system_mgmt.tasks import schedule_im_account_association_sync

    with patch("apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay") as mock_delay:
        result = schedule_im_account_association_sync(channel.account_association_id)

    assert result["result"] is True
    mock_delay.assert_called_once()


@pytest.mark.django_db
def test_pending_association_completes_first_sync_through_schedule_path(channel, user):
    from apps.system_mgmt.tasks import schedule_im_account_association_sync

    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_users": [{"user_id": "ou_123", "email": "tester@example.com", "name": "Tester"}]},
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        with patch("apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay") as mock_delay:

            def run_immediately(run_id):
                return execute_im_notification_sync_run(run_id)

            mock_delay.side_effect = run_immediately
            result = schedule_im_account_association_sync(channel.account_association_id)

    channel.refresh_from_db()
    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])

    assert result["result"] is True
    assert run.trigger_mode == "schedule"
    assert run.status == "success"
    assert channel.status == CHANNEL_STATUS_READY


def _rendered_log(record):
    return _LOG_FORMATTER.format(record)


def _assert_one_error(caplog, template, args, message, forbidden):
    matches = [record for record in caplog.records if record.msg == template]
    assert len(matches) == 1
    record = matches[0]
    assert record.levelno == logging.ERROR
    assert record.args == args
    assert record.getMessage() == message
    assert record.exc_info in (None, (None, None, None))
    rendered = _rendered_log(record)
    blob = "\n".join([record.getMessage(), rendered, caplog.text])
    for secret in forbidden:
        assert secret not in blob
    assert sum(item.levelno >= logging.ERROR for item in caplog.records) == 1
    return record


@pytest.mark.django_db
def test_external_user_pull_failure_logs_one_error_and_keeps_ready_result(channel, caplog):
    run = IMNotificationSyncRun.objects.create(
        account_association=channel.account_association,
        status="running",
        summary="started",
        locked_config_snapshot={
            "integration_instance_id": channel.integration_instance_id,
            "provider_key": "feishu",
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
        },
    )
    failed = CapabilityExecutionResult.failed_result(
        _SUMMARY_SENTINEL,
        code="provider.unavailable",
        payload={"body": _PAYLOAD_SENTINEL},
    )

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=failed,
    ):
        result = execute_im_notification_sync_run(run.id)

    run.refresh_from_db()
    channel.account_association.refresh_from_db()
    assert result == {"result": False, "message": _SUMMARY_SENTINEL}
    assert run.status == "failed"
    assert run.summary == _SUMMARY_SENTINEL
    assert run.payload["payload"]["body"] == _PAYLOAD_SENTINEL
    assert channel.account_association.status == "ready"
    _assert_one_error(
        caplog,
        EXTERNAL_CALL_FAILED,
        (run.id, channel.account_association_id, "list_external_users", "provider.unavailable", "feishu", failed.request_id),
        (
            "event=im_account_association_external_call_failed "
            f"run_id={run.id} association_id={channel.account_association_id} "
            f"failed_stage=list_external_users error_type=provider.unavailable provider_key=feishu request_id={failed.request_id}"
        ),
        (_SUMMARY_SENTINEL, _PAYLOAD_SENTINEL, "plain-secret"),
    )


@pytest.mark.django_db
def test_external_send_failure_logs_one_error_and_returns_provider_summary(channel, user, caplog):
    IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
        user=user,
        external_identity_key="open_id",
        external_identity_value="ou_identity",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={},
        external_snapshot={"user_id": "ou_123"},
    )
    failed = CapabilityExecutionResult.failed_result(
        _SUMMARY_SENTINEL,
        code="provider.unavailable",
        payload={"body": _PAYLOAD_SENTINEL},
    )

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=failed,
    ) as mock_execute:
        result = send_im_notification(channel.id, "secret-sentinel-TITLE", "secret-sentinel-BODY", [user.id])

    assert result["result"] is False
    assert result["message"] == _SUMMARY_SENTINEL
    assert result["data"]["skipped"] == []
    assert mock_execute.call_args.kwargs["receive_ids"] == ["ou_123"]
    _assert_one_error(
        caplog,
        EXTERNAL_SEND_FAILED,
        (channel.id, channel.account_association_id, "send_message", "provider.unavailable", "feishu", failed.request_id),
        (
            "event=im_notification_external_send_failed "
            f"channel_id={channel.id} association_id={channel.account_association_id} "
            f"failed_stage=send_message error_type=provider.unavailable provider_key=feishu request_id={failed.request_id}"
        ),
        (_SUMMARY_SENTINEL, _PAYLOAD_SENTINEL, "secret-sentinel-TITLE", "secret-sentinel-BODY", "plain-secret"),
    )


@pytest.mark.django_db
def test_external_send_success_omits_provider_summary(channel, user, caplog):
    IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
        user=user,
        external_identity_key="open_id",
        external_identity_value="ou_identity",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={},
        external_snapshot={"user_id": "ou_123"},
    )
    sent = CapabilityExecutionResult.success_result(_SUMMARY_SENTINEL, payload={"body": _PAYLOAD_SENTINEL})

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=sent,
    ) as mock_execute:
        result = send_im_notification(channel.id, "secret-sentinel-TITLE", "secret-sentinel-BODY", [user.id])

    assert result["result"] is True
    assert result["message"] == _SUMMARY_SENTINEL
    assert result["data"]["skipped"] == []
    assert result["data"]["payload"]["body"] == _PAYLOAD_SENTINEL
    assert mock_execute.call_args.kwargs["receive_ids"] == ["ou_123"]
    matches = [record for record in caplog.records if record.msg == EXTERNAL_SEND_SUCCEEDED]
    assert len(matches) == 1
    record = matches[0]
    assert record.levelno == logging.INFO
    assert record.args == ("send_im_notification", channel.id, channel.account_association_id, "feishu", 1, 0)
    assert record.getMessage() == (
        "event=im_notification_external_send_succeeded "
        f"log_name=send_im_notification channel_id={channel.id} association_id={channel.account_association_id} "
        "provider_key=feishu recipient_count=1 skipped=0"
    )
    assert record.exc_info in (None, (None, None, None))
    rendered = _LOG_FORMATTER.format(record)
    blob = "\n".join([record.getMessage(), rendered, caplog.text])
    for secret in (_SUMMARY_SENTINEL, _PAYLOAD_SENTINEL, "secret-sentinel-TITLE", "secret-sentinel-BODY", "plain-secret"):
        assert secret not in blob
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)


def test_retired_channel_schedule_warns_and_keeps_the_same_result(caplog):
    from apps.system_mgmt.tasks import schedule_im_notification_sync

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        result = schedule_im_notification_sync(12)

    assert result == {"result": False, "message": "IM notification channel schedule has moved to account association"}
    matches = [
        record
        for record in caplog.records
        if record.msg == "event=im_notification_channel_schedule_skipped channel_id=%s failed_stage=%s error_type=%s"
    ]
    assert len(matches) == 1
    assert matches[0].levelno == logging.WARNING
    assert matches[0].args == (12, "schedule", "moved")
    assert matches[0].getMessage() == ("event=im_notification_channel_schedule_skipped channel_id=12 failed_stage=schedule error_type=moved")
    assert matches[0].exc_info in (None, (None, None, None))
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.django_db
def test_scheduled_association_skip_warns_without_creating_a_run(channel, caplog):
    from apps.system_mgmt.tasks import schedule_im_account_association_sync

    channel.integration_instance.capability_enabled = {"im_notification": False}
    channel.integration_instance.save(update_fields=["capability_enabled"])

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay"
    ) as mock_delay:
        result = schedule_im_account_association_sync(channel.account_association_id)

    assert result == {"result": False, "message": "IM notification capability is not ready"}
    assert IMNotificationSyncRun.objects.filter(account_association=channel.account_association).count() == 0
    mock_delay.assert_not_called()
    matches = [
        record
        for record in caplog.records
        if record.msg == "event=im_account_association_schedule_skipped association_id=%s failed_stage=%s error_type=%s"
    ]
    assert len(matches) == 1
    assert matches[0].levelno == logging.WARNING
    assert matches[0].args == (channel.account_association_id, "schedule", "capability_not_ready")
    assert matches[0].getMessage() == (
        "event=im_account_association_schedule_skipped "
        f"association_id={channel.account_association_id} failed_stage=schedule error_type=capability_not_ready"
    )
    assert "IM notification capability is not ready" not in matches[0].getMessage()
    assert matches[0].exc_info in (None, (None, None, None))


_DISCARD_TEMPLATE = "event=im_account_association_sync_result_discarded run_id=%s association_id=%s failed_stage=%s error_type=%s"
_SYNC_COMPLETED = (
    "execute_im_notification_sync_run: sync completed, run_id=%s, association_id=%s, status=%s, "
    "total_external_users=%s, matched=%s, unmatched=%s, conflict=%s"
)
_INSTANCE_MISSING = "event=im_account_association_sync_instance_missing run_id=%s association_id=%s failed_stage=%s error_type=%s"


def _kept_mapping(channel, user):
    return IMNotificationUserMapping.objects.create(
        account_association=channel.account_association,
        user=user,
        external_identity_key="user_id",
        external_identity_value="old-keep",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={},
        external_snapshot={"user_id": "old-keep", "email": "tester@example.com"},
    )


def _assert_stale_result_not_restored(channel, run_id, caplog):
    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    run = IMNotificationSyncRun.objects.get(id=run_id)
    mappings = list(IMNotificationUserMapping.objects.filter(account_association=channel.account_association))

    assert channel.account_association.status == "needs_resync"
    assert channel.status == "needs_resync"
    assert [item.external_identity_value for item in mappings] == ["old-keep"]
    assert run.status == "success"
    assert run.matched_count == 1
    assert run.finished_at is not None
    matches = [record for record in caplog.records if record.msg == _DISCARD_TEMPLATE]
    assert len(matches) == 1
    assert matches[0].levelno == logging.WARNING
    assert matches[0].args == (run_id, channel.account_association_id, "apply_result", "config_changed")
    assert matches[0].getMessage() == (
        "event=im_account_association_sync_result_discarded "
        f"run_id={run_id} association_id={channel.account_association_id} "
        "failed_stage=apply_result error_type=config_changed"
    )
    assert matches[0].exc_info in (None, (None, None, None))
    assert not any(record.msg == _SYNC_COMPLETED for record in caplog.records)
    rendered = _LOG_FORMATTER.format(matches[0])
    for secret in ("plain-secret", "cli_changed", "ou_new"):
        assert secret not in rendered


@pytest.mark.django_db
def test_completed_update_does_not_restore_result_after_match_field_changes(channel, user, caplog):
    _kept_mapping(channel, user)
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    channel.account_association.platform_match_field = "username"
    channel.account_association.save(update_fields=["platform_match_field"])
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_users": [{"user_id": "ou_new", "email": "tester@example.com", "name": "Tester"}]},
    )

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=payload,
    ):
        result = execute_im_notification_sync_run(run_id)

    assert result["result"] is True
    _assert_stale_result_not_restored(channel, run_id, caplog)


@pytest.mark.django_db
def test_completed_update_does_not_restore_result_after_app_identity_changes(channel, user, caplog):
    _kept_mapping(channel, user)
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    channel.integration_instance.config = {**channel.integration_instance.config, "app_id": "cli_changed"}
    channel.integration_instance.save(update_fields=["config"])
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_users": [{"user_id": "ou_new", "email": "tester@example.com", "name": "Tester"}]},
    )

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=payload,
    ):
        result = execute_im_notification_sync_run(run_id)

    assert result["result"] is True
    _assert_stale_result_not_restored(channel, run_id, caplog)


_WRITE_SKIPPED_TEMPLATE = "event=im_account_association_sync_write_skipped run_id=%s association_id=%s"
_NO_LONGER_RUNNING = "IM account association update is no longer running"


def _finish_run(run_id):
    run = IMNotificationSyncRun.objects.get(id=run_id)
    run.status = "success"
    run.summary = "later result"
    run.matched_count = 7
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "summary", "matched_count", "finished_at"])
    return run


def _assert_later_result_kept(channel, run_id, caplog):
    run = IMNotificationSyncRun.objects.get(id=run_id)
    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    mappings = list(IMNotificationUserMapping.objects.filter(account_association=channel.account_association))
    assert channel.account_association.status == "ready"
    assert channel.status == "ready"
    assert [item.external_identity_value for item in mappings] == ["later-keep"]
    assert run.status == "success"
    assert run.summary == "later result"
    assert run.matched_count == 7
    matches = [record for record in caplog.records if record.msg == _WRITE_SKIPPED_TEMPLATE]
    assert len(matches) == 1
    assert matches[0].levelno == logging.WARNING
    assert matches[0].args == (run_id, channel.account_association_id)
    assert matches[0].getMessage() == (
        f"event=im_account_association_sync_write_skipped run_id={run_id} association_id={channel.account_association_id}"
    )
    assert "later result" not in matches[0].getMessage()
    assert "plain-secret" not in _LOG_FORMATTER.format(matches[0])


@pytest.mark.django_db
def test_finished_update_does_not_overwrite_a_later_result(channel, user, caplog):
    mapping = _kept_mapping(channel, user)
    mapping.external_identity_value = "later-keep"
    mapping.save(update_fields=["external_identity_value"])
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    _finish_run(run_id)
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_users": [{"user_id": "ou_late", "email": "tester@example.com", "name": "Tester"}]},
    )

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=payload,
    ):
        result = execute_im_notification_sync_run(run_id)

    assert result == {"result": False, "message": _NO_LONGER_RUNNING}
    _assert_later_result_kept(channel, run_id, caplog)


@pytest.mark.django_db
def test_finished_update_does_not_overwrite_result_when_pull_fails(channel, user, caplog):
    mapping = _kept_mapping(channel, user)
    mapping.external_identity_value = "later-keep"
    mapping.save(update_fields=["external_identity_value"])
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    _finish_run(run_id)
    failed = CapabilityExecutionResult.failed_result("pull failed", code="provider.unavailable")

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute",
        return_value=failed,
    ):
        result = execute_im_notification_sync_run(run_id)

    assert result == {"result": False, "message": _NO_LONGER_RUNNING}
    _assert_later_result_kept(channel, run_id, caplog)


@pytest.mark.django_db
def test_failed_update_stops_using_result_after_app_identity_changes(channel, user):
    _kept_mapping(channel, user)
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    channel.integration_instance.config = {**channel.integration_instance.config, "app_id": "cli_changed"}
    channel.integration_instance.save(update_fields=["config"])
    failed = CapabilityExecutionResult.failed_result("pull failed", code="provider.unavailable")

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=failed):
        result = execute_im_notification_sync_run(run_id)

    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    run = IMNotificationSyncRun.objects.get(id=run_id)
    mappings = list(IMNotificationUserMapping.objects.filter(account_association=channel.account_association))
    assert result == {"result": False, "message": "pull failed"}
    assert channel.account_association.status == "needs_resync"
    assert channel.status == "needs_resync"
    assert [item.external_identity_value for item in mappings] == ["old-keep"]
    assert run.status == "failed"
    assert run.summary == "pull failed"


@pytest.mark.django_db
def test_send_keeps_conflict_reason_when_diagnostic_list_is_truncated(channel, user, monkeypatch):
    monkeypatch.setattr("apps.system_mgmt.services.im_notification_service.MAX_DIAGNOSTIC_ISSUES", 0)
    first = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="conflict-first",
        display_name="Conflict First",
        email="shared@example.com",
        password="",
        domain="domain.com",
    )
    second = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="conflict-second",
        display_name="Conflict Second",
        email="shared@example.com",
        password="",
        domain="domain.com",
    )
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    payload = CapabilityExecutionResult.success_result(
        "ok",
        payload={
            "external_users": [
                {"user_id": "ou_tester", "email": "tester@example.com", "name": "Tester"},
                {"user_id": "ou_shared", "email": "shared@example.com", "name": "Shared"},
            ]
        },
    )

    with patch("apps.system_mgmt.services.im_notification_service.RuntimeApplicationService.execute", return_value=payload):
        execute_im_notification_sync_run(run_id)

    run = IMNotificationSyncRun.objects.get(id=run_id)
    channel.account_association.refresh_from_db()
    assert run.payload["conflict_issues"] == []
    assert run.payload["conflict_user_ids"] == sorted([first.id, second.id])
    assert channel.account_association.status == "ready"

    result = send_im_notification(channel.id, "Title", "Body", [second.id])

    assert result["result"] is False
    assert result["data"]["skipped"] == [{"receiver": "conflict-second", "reason": "conflict"}]


@pytest.mark.django_db
def test_send_reads_conflict_issues_when_full_user_ids_are_absent(channel, user):
    other = User.objects.create(
        user_id=str(uuid.uuid4()),
        username="plain-user",
        display_name="Plain User",
        email="plain@example.com",
        password="",
        domain="domain.com",
    )
    IMNotificationSyncRun.objects.create(
        account_association=channel.account_association,
        status="partial",
        payload={"conflict_issues": [{"platform_user_ids": [user.id]}]},
    )

    result = send_im_notification(channel.id, "Title", "Body", [user.id, other.id])

    assert result["data"]["skipped"] == [
        {"receiver": "tester", "reason": "conflict"},
        {"receiver": "plain-user", "reason": "unassociated"},
    ]


@pytest.mark.django_db
def test_missing_instance_logs_one_error_and_keeps_the_ready_result(channel, user, caplog):
    _kept_mapping(channel, user)
    run_id = create_account_association_sync_run(channel.account_association_id)["data"]["run_id"]
    run = IMNotificationSyncRun.objects.get(id=run_id)
    run.locked_config_snapshot = {**run.locked_config_snapshot, "integration_instance_id": 0}
    run.save(update_fields=["locked_config_snapshot"])

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        result = execute_im_notification_sync_run(run_id)

    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    run.refresh_from_db()
    assert result == {"result": False, "message": "Integration instance not found"}
    assert channel.account_association.status == "ready"
    assert channel.status == "ready"
    assert IMNotificationUserMapping.objects.filter(account_association=channel.account_association).count() == 1
    assert run.status == "failed"
    assert run.summary == "Integration instance not found"
    matches = [record for record in caplog.records if record.msg == _INSTANCE_MISSING]
    assert len(matches) == 1
    assert matches[0].levelno == logging.ERROR
    assert matches[0].args == (run_id, channel.account_association_id, "load_instance", "instance_missing")
    assert matches[0].getMessage() == (
        "event=im_account_association_sync_instance_missing "
        f"run_id={run_id} association_id={channel.account_association_id} "
        "failed_stage=load_instance error_type=instance_missing"
    )
    assert matches[0].exc_info in (None, (None, None, None))
    rendered = _LOG_FORMATTER.format(matches[0])
    assert "plain-secret" not in rendered
    assert sum(record.levelno >= logging.ERROR for record in caplog.records) == 1


def _save_instance_config(instance, app_id):
    from apps.system_mgmt.serializers.integration_instance_serializer import IntegrationInstanceSerializer

    serializer = IntegrationInstanceSerializer(instance, data={"config": {"app_id": app_id}}, partial=True)
    assert serializer.is_valid(), serializer.errors
    return serializer.save()


@pytest.mark.django_db
def test_identity_change_invalidates_associations_in_the_same_save(channel):
    saved = _save_instance_config(channel.integration_instance, "cli_new")

    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    assert saved.get_runtime_config()["app_id"] == "cli_new"
    assert channel.account_association.status == "needs_resync"
    assert channel.status == "needs_resync"


@pytest.mark.django_db
def test_identity_invalidation_failure_keeps_the_previous_instance_config(channel):
    with patch(
        "apps.system_mgmt.serializers.integration_instance_serializer.im_notification_service.invalidate_account_associations_for_identity_change",
        side_effect=RuntimeError("invalidate failed"),
    ):
        with pytest.raises(RuntimeError, match="invalidate failed"):
            _save_instance_config(channel.integration_instance, "cli_new")

    channel.integration_instance.refresh_from_db()
    channel.account_association.refresh_from_db()
    channel.refresh_from_db()
    assert channel.integration_instance.get_runtime_config()["app_id"] == "cli_xxx"
    assert channel.account_association.status == "ready"
    assert channel.status == "ready"

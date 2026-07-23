import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

import pytest
from django.db import close_old_connections, connections

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.reconcile import pause_group_for_closed_incident, reconcile_incident_im_group, resume_group_for_reopened_incident
from apps.alerts.service.outbox import deliver_outbox_record
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_delivery_fixtures"]


def test_summary_without_public_web_url_fails_closed_without_provider(group, settings):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    settings.WEB_BASE_URL = ""
    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["external_chat_id", "current_stage"])

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        deliver_summary(group.id)

    group.refresh_from_db()
    execute.assert_not_called()
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.status == IncidentIMGroup.Status.DEGRADED
    assert group.last_error_code == "IM_WEB_BASE_URL_MISSING"


@pytest.mark.parametrize(
    "web_base_url",
    [
        "/bk-lite",
        "bk-lite.example.com",
        "ftp://bk-lite.example.com",
        "http://localhost",
        "https://localhost:8443",
        "http://127.0.0.1:8000",
        "https://[::1]",
        "http://10.0.0.1",
        "https://192.168.1.10",
        "http://0.0.0.0:8000",
    ],
)
def test_summary_rejects_non_public_absolute_web_url_without_provider(group, settings, web_base_url):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    settings.WEB_BASE_URL = web_base_url
    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["external_chat_id", "current_stage"])

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        deliver_summary(group.id)

    group.refresh_from_db()
    execute.assert_not_called()
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.status == IncidentIMGroup.Status.DEGRADED
    assert group.last_error_code == "IM_WEB_BASE_URL_INVALID"
    assert group.last_error_message == "WEB_BASE_URL 必须配置为可从飞书访问的 HTTP(S) 绝对地址"


@pytest.mark.django_db
def test_summary_failure_is_terminal_and_completes_as_partial(group):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["external_chat_id", "current_stage"])
    failed = CapabilityExecutionResult.failed_result("message rejected", code="provider.permission_denied")
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=failed,
    ):
        deliver_summary(group.id)

    group.refresh_from_db()
    assert group.current_stage == "completed"
    assert group.status == "active_partial"
    assert group.last_error_code == "provider.permission_denied"


@pytest.mark.django_db
def test_retryable_summary_result_raises_for_outbox_retry(group):
    from apps.alerts.service.incident_im.delivery import IncidentIMRetryableError, deliver_summary

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    limited = CapabilityExecutionResult.failed_result("rate limited", code="provider.rate_limited", retryable=True)
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=limited,
    ):
        with pytest.raises(IncidentIMRetryableError, match="rate limited"):
            deliver_summary(group.id)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pause_reason", [IncidentIMGroup.PauseReason.MANUAL, IncidentIMGroup.PauseReason.INCIDENT_CLOSED,],
)
def test_queued_summary_paused_before_delivery_finishes_without_provider(group, pause_reason):
    group.external_chat_id = "oc_1"
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = pause_reason
    group.resume_after_reopen = True
    group.save(
        update_fields=["external_chat_id", "status", "pause_reason", "resume_after_reopen",]
    )
    if pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED:
        group.incident.status = IncidentStatus.CLOSED
        group.incident.save(update_fields=["status"])
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.send_summary",
        payload={"group_id": str(group.id)},
        idempotency_key=f"summary-paused-{pause_reason}-{uuid.uuid4().hex}",
    )

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        assert deliver_outbox_record(outbox.id) is True

    execute.assert_not_called()
    group.refresh_from_db()
    outbox.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == pause_reason
    assert group.resume_after_reopen is True
    assert outbox.status == AlertOutbox.Status.DELIVERED


@pytest.mark.django_db
@pytest.mark.parametrize("resume_mode", ["manual", "incident_reopen"])
def test_consumed_paused_summary_is_requeued_with_stable_provider_uuid(group, resume_mode):
    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.continuous_sync_enabled = False
    group.save(
        update_fields=["external_chat_id", "current_stage", "continuous_sync_enabled",]
    )
    if resume_mode == "incident_reopen":
        group.incident.status = IncidentStatus.CLOSED
        group.incident.save(update_fields=["status"])
        pause_group_for_closed_incident(group.incident_id)
    else:
        IncidentIMGroup.objects.filter(pk=group.id).update(
            status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL, resume_after_reopen=False,
        )
    consumed = AlertOutbox.objects.create(
        kind="incident_im_group.send_summary", payload={"group_id": str(group.id)}, idempotency_key=f"incident-im-group:{group.id}:send-summary",
    )

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        assert deliver_outbox_record(consumed.id) is True
    execute.assert_not_called()

    if resume_mode == "manual":
        IncidentIMGroup.objects.filter(pk=group.id).update(
            status=IncidentIMGroup.Status.ACTIVE, pause_reason="", resume_after_reopen=False,
        )
        reconcile_incident_im_group(group.incident_id, resume_create=True)
    else:
        group.incident.status = IncidentStatus.PROCESSING
        group.incident.save(update_fields=["status", "updated_at"])
        resume_group_for_reopened_incident(group.incident_id)
        reconcile_outbox = AlertOutbox.objects.get(kind="incident_im_group.reconcile", status=AlertOutbox.Status.PENDING,)
        assert deliver_outbox_record(reconcile_outbox.id) is True

    reconcile_incident_im_group(group.incident_id, resume_create=True)
    replacements = AlertOutbox.objects.filter(
        kind="incident_im_group.send_summary", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,
    ).exclude(pk=consumed.pk)
    assert replacements.count() == 1
    replacement = replacements.get()
    assert replacement.idempotency_key != consumed.idempotency_key

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=CapabilityExecutionResult.success_result("sent"),
    ) as execute:
        assert deliver_outbox_record(replacement.id) is True

    assert execute.call_args.kwargs["idempotency_key"] == f"bklite-summary-{group.id.hex}"


@pytest.mark.django_db
@pytest.mark.parametrize("pause_mode", ["manual", "incident_closed"])
def test_terminal_create_ack_preserves_pause_then_resume_converges_to_create_failed(group, pending_members, pause_mode):
    terminal = CapabilityExecutionResult.failed_result("permission denied", code="provider.permission_denied",)

    def fail_after_pause(*_args, **_kwargs):
        if pause_mode == "manual":
            IncidentIMGroup.objects.filter(pk=group.id).update(
                status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL, resume_after_reopen=False,
            )
        else:
            group.incident.status = IncidentStatus.CLOSED
            group.incident.save(update_fields=["status"])
            pause_group_for_closed_incident(group.incident_id)
        return terminal

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=fail_after_pause,
    ):
        from apps.alerts.service.incident_im.delivery import deliver_create_group

        deliver_create_group(group.id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == (IncidentIMGroup.PauseReason.MANUAL if pause_mode == "manual" else IncidentIMGroup.PauseReason.INCIDENT_CLOSED)
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_error_code == "provider.permission_denied"

    reconcile_incident_im_group(group.incident_id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED

    if pause_mode == "manual":
        IncidentIMGroup.objects.filter(pk=group.id).update(
            status=IncidentIMGroup.Status.ACTIVE, pause_reason="",
        )
        reconcile_incident_im_group(group.incident_id)
    else:
        group.incident.status = IncidentStatus.PROCESSING
        group.incident.save(update_fields=["status", "updated_at"])
        resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.CREATE_FAILED
    assert group.pause_reason == ""
    assert group.last_error_code == "provider.permission_denied"
    assert not AlertOutbox.objects.filter(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("pause_mode", ["manual", "incident_closed"])
def test_terminal_add_ack_preserves_pause_then_resume_converges_to_degraded(group, pending_members, pause_mode):
    group.external_chat_id = "oc_deleted"
    group.save(update_fields=["external_chat_id"])
    terminal = CapabilityExecutionResult.failed_result("group missing", code="provider.group_not_found",)

    def fail_after_pause(*_args, **_kwargs):
        if pause_mode == "manual":
            IncidentIMGroup.objects.filter(pk=group.id).update(
                status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL, resume_after_reopen=False,
            )
        else:
            group.incident.status = IncidentStatus.CLOSED
            group.incident.save(update_fields=["status"])
            pause_group_for_closed_incident(group.incident_id)
        return terminal

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=fail_after_pause,
    ):
        from apps.alerts.service.incident_im.delivery import deliver_add_members

        deliver_add_members(group.id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == (IncidentIMGroup.PauseReason.MANUAL if pause_mode == "manual" else IncidentIMGroup.PauseReason.INCIDENT_CLOSED)
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_error_code == "provider.group_not_found"

    reconcile_incident_im_group(group.incident_id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED

    if pause_mode == "manual":
        IncidentIMGroup.objects.filter(pk=group.id).update(
            status=IncidentIMGroup.Status.ACTIVE, pause_reason="",
        )
        reconcile_incident_im_group(group.incident_id)
    else:
        group.incident.status = IncidentStatus.PROCESSING
        group.incident.save(update_fields=["status", "updated_at"])
        resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.DEGRADED
    assert group.pause_reason == ""
    assert group.last_error_code == "provider.group_not_found"
    assert not AlertOutbox.objects.filter(
        kind="incident_im_group.add_members", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,
    ).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "pause_reason", [IncidentIMGroup.PauseReason.MANUAL, IncidentIMGroup.PauseReason.INCIDENT_CLOSED,],
)
def test_summary_ack_after_pause_preserves_authoritative_pause(group, pause_reason):
    if connections["default"].vendor != "sqlite":
        pytest.skip("当前 Barrier 合同使用 SQLite 独立连接验证")
    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["external_chat_id", "current_stage"])
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.send_summary",
        payload={"group_id": str(group.id)},
        idempotency_key=f"summary-inflight-pause-{pause_reason}-{uuid.uuid4().hex}",
    )
    barrier = Barrier(2)

    def provider_ack_after_pause(*args, **kwargs):
        barrier.wait(timeout=10)
        barrier.wait(timeout=10)
        return CapabilityExecutionResult.success_result("sent")

    def deliver_from_independent_connection():
        close_old_connections()
        try:
            return deliver_outbox_record(outbox.id)
        finally:
            connections.close_all()

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=provider_ack_after_pause,) as execute:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(deliver_from_independent_connection)
            try:
                barrier.wait(timeout=10)
                if pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED:
                    group.incident.status = IncidentStatus.CLOSED
                    group.incident.save(update_fields=["status"])
                    pause_group_for_closed_incident(group.incident_id)
                    expected_resume = True
                else:
                    IncidentIMGroup.objects.filter(pk=group.id).update(
                        status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL, resume_after_reopen=False,
                    )
                    expected_resume = False
                barrier.wait(timeout=10)
                assert future.result(timeout=20) is True
            finally:
                barrier.abort()
                if not future.done():
                    future.cancel()

    assert execute.call_count == 1
    group.refresh_from_db()
    outbox.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == pause_reason
    assert group.resume_after_reopen is expected_resume
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_sync_at is not None
    assert outbox.status == AlertOutbox.Status.DELIVERED


@pytest.mark.django_db
@pytest.mark.parametrize("gap_status", ["waiting", "pending", "adding", "failed"])
def test_summary_keeps_group_partial_for_every_non_joined_member_state(group, gap_status):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    group.incident.collaborators = [f"gap-{gap_status}"]
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.create(
        group=group,
        username=f"gap-{gap_status}",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        external_id="ou_gap",
        external_id_type="open_id",
        sync_status=gap_status,
    )
    result = CapabilityExecutionResult.success_result("sent")
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,
    ):
        deliver_summary(group.id)

    group.refresh_from_db()
    assert group.status == "active_partial"


@pytest.mark.django_db
def test_summary_ignores_removed_unjoined_history_when_computing_active_status(group):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        external_id="ou_alice",
        external_id_type="open_id",
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="former",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        external_id="ou_former",
        external_id_type="open_id",
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )
    result = CapabilityExecutionResult.success_result("sent")
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,
    ):
        deliver_summary(group.id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE


@pytest.mark.django_db
def test_summary_reuses_stable_provider_uuid_after_external_ack_before_local_confirmation_crash(group,):
    from apps.alerts.service.incident_im import delivery

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    result = CapabilityExecutionResult.success_result("sent")
    real_lock_group = delivery._lock_group
    lock_count = 0

    def crash_on_confirmation(group_id):
        nonlocal lock_count
        lock_count += 1
        if lock_count == 2:
            raise RuntimeError("crash before local confirmation")
        return real_lock_group(group_id)

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery._lock_group", side_effect=crash_on_confirmation,
    ):
        with pytest.raises(RuntimeError, match="crash before local confirmation"):
            delivery.deliver_summary(group.id)

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,) as retry_execute:
        delivery.deliver_summary(group.id)

    first_key = execute.call_args.kwargs["idempotency_key"]
    retry_key = retry_execute.call_args.kwargs["idempotency_key"]
    assert first_key == retry_key == f"bklite-summary-{group.id.hex}"

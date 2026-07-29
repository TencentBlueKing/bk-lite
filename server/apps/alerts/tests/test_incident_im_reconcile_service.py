import uuid
from unittest import mock

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.delivery import deliver_add_members
from apps.alerts.service.incident_im.reconcile import reconcile_incident_im_group
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tests.incident_im_reconcile_fixtures import map_user as _map_user
from apps.system_mgmt.models import IMNotificationUserMapping, User
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_reconcile_fixtures"]


def test_retryable_add_members_emits_safe_business_event_before_outbox_retry(
    group, channel,
):
    from apps.alerts.service.incident_im.delivery import IncidentIMRetryableError

    _map_user(channel, "alice")
    member = IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    limited = CapabilityExecutionResult.failed_result(
        "rate limited", code="provider.rate_limited", retryable=True
    )
    events = []
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=limited,
    ), mock.patch(
        "apps.alerts.service.incident_im.delivery.emit_incident_im_event",
        side_effect=lambda event, **fields: events.append((event, fields)),
    ):
        with pytest.raises(IncidentIMRetryableError, match="rate limited"):
            deliver_add_members(group.id)

    assert events == [
        (
            "incident_im_member_batch",
            {
                "group_id": str(group.id),
                "incident_id": group.incident_id,
                "operation": "add_members",
                "result": "retrying",
                "error_code": "provider.rate_limited",
                "retryable": True,
                "member_count": 1,
            },
        )
    ]
    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.PENDING


@pytest.mark.django_db
def test_manual_resume_create_seam_requeues_initial_create(incident, channel):
    group = IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="[Incident] 首次创建暂停",
        external_chat_id="",
        status=IncidentIMGroup.Status.ACTIVE_PARTIAL,
        current_stage=IncidentIMGroup.Stage.CREATING_CHAT,
        continuous_sync_enabled=False,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )

    reconcile_incident_im_group(
        incident.id, resume_create=True,
    )

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.current_stage == IncidentIMGroup.Stage.QUEUED
    assert AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)},).count() == 1


@pytest.mark.django_db
def test_new_collaborator_enqueues_add_when_continuous_sync_enabled(group, channel):
    _map_user(channel, "alice")
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])

    reconcile_incident_im_group(group.incident_id)

    member = group.members.get(username="bob")
    assert member.sync_status == IncidentIMMember.SyncStatus.PENDING
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    outbox = AlertOutbox.objects.get(kind="incident_im_group.add_members")
    assert outbox.payload["group_id"] == str(group.id)
    assert outbox.payload["member_pks"] == list(
        group.members.filter(mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.PENDING,)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    assert len(outbox.payload["batch_digest"]) == 64


@pytest.mark.django_db
def test_new_payload_pending_add_prevents_reconcile_from_enqueuing_duplicate(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    AlertOutbox.objects.create(
        kind="incident_im_group.add_members",
        payload={"group_id": str(group.id), "member_pks": [member.pk], "batch_digest": "existing",},
        idempotency_key=f"existing-new-add-{uuid.uuid4().hex}",
    )

    reconcile_incident_im_group(group.incident_id)

    assert AlertOutbox.objects.filter(
        kind="incident_im_group.add_members", payload__group_id=str(group.id),
    ).count() == 1


@pytest.mark.django_db
def test_removed_collaborator_is_not_deleted_or_enqueued_for_removal(group):
    joined = IncidentIMMember.objects.create(
        group=group,
        username="former-user",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )

    reconcile_incident_im_group(group.incident_id)

    assert group.members.filter(pk=joined.pk, sync_status="joined").exists()
    assert not AlertOutbox.objects.filter(kind__contains="remove").exists()


@pytest.mark.django_db
def test_mapping_completion_promotes_waiting_member_and_enqueues(group, channel):
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    User.objects.create(username="bob", display_name="Bob", password="test-password")
    reconcile_incident_im_group(group.incident_id)
    waiting = group.members.get(username="bob")
    assert waiting.sync_status == IncidentIMMember.SyncStatus.WAITING
    AlertOutbox.objects.all().delete()
    user = User.objects.get(username="bob")
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="open_id",
        external_identity_value="identity-bob",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_bob"},
    )

    reconcile_incident_im_group(group.incident_id)

    waiting.refresh_from_db()
    assert waiting.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_real_invalid_delivery_is_not_retried_by_periodic_reconcile(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    invalid = CapabilityExecutionResult(success=True, partial_success=True, summary="partial", payload={"invalid_member_ids": ["ou_bob"]},)
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=invalid,), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_add_members(group.id)

    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.FAILED
    for _ in range(3):
        reconcile_incident_im_group(group.incident_id)
    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_new_pending_member_delivery_does_not_retry_old_failed_member(group):
    group.incident.collaborators = ["pending"]
    group.incident.save(update_fields=["collaborators"])
    failed = IncidentIMMember.objects.create(
        group=group,
        username="failed",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_failed",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )
    pending = IncidentIMMember.objects.create(
        group=group,
        username="pending",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_pending",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_add_members(group.id)

    assert execute.call_args.kwargs["member_ids"] == [pending.external_id]
    failed.refresh_from_db()
    assert failed.sync_status == IncidentIMMember.SyncStatus.FAILED


@pytest.mark.django_db
def test_force_delivery_promotes_mapped_failed_member_and_enqueues(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
        last_error_message="外部用户标识无效",
    )

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert member.last_error_code == ""
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_group_force_retries_exhausted_add_delivery_with_stable_resume_event(group, channel):
    from apps.alerts.service.incident_im.delivery import enqueue_add_members_batch

    _map_user(channel, "bob")
    group.incident.operator = []
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["operator", "collaborators"])
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    assert enqueue_add_members_batch(group) is True
    exhausted = AlertOutbox.objects.get(kind="incident_im_group.add_members")
    exhausted.status = AlertOutbox.Status.FAILED
    exhausted.save(update_fields=["status"])
    group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
    group.current_stage = IncidentIMGroup.Stage.COMPLETED
    group.last_sync_at = timezone.now()
    group.last_error_code = "IM_DELIVERY_EXHAUSTED"
    group.last_error_message = "投递重试已耗尽"
    group.save(update_fields=["status", "current_stage", "last_sync_at", "last_error_code", "last_error_message"])

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    retry = AlertOutbox.objects.exclude(pk=exhausted.pk).get(kind="incident_im_group.add_members")
    assert retry.idempotency_key == f"{exhausted.idempotency_key}:resume:{exhausted.pk}"
    assert retry.payload["member_pks"] == [member.pk]

    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,):
        assert deliver_outbox_record(retry.pk) is True

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert group.last_error_code == ""
    assert group.last_error_message == ""


@pytest.mark.django_db
def test_new_payload_pending_add_prevents_force_retry_from_enqueuing_duplicate(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )
    AlertOutbox.objects.create(
        kind="incident_im_group.add_members",
        payload={"group_id": str(group.id), "member_pks": [member.pk],},
        idempotency_key=f"existing-force-add-{uuid.uuid4().hex}",
    )

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert AlertOutbox.objects.filter(
        kind="incident_im_group.add_members", payload__group_id=str(group.id),
    ).count() == 1


@pytest.mark.django_db
def test_continuous_sync_off_keeps_pending_without_delivery(group, channel):
    group.continuous_sync_enabled = False
    group.save(update_fields=["continuous_sync_enabled"])
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])

    reconcile_incident_im_group(group.incident_id)

    assert group.members.get(username="bob").sync_status == IncidentIMMember.SyncStatus.PENDING
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_force_delivery_only_bypasses_continuous_sync_off(group, channel):
    group.continuous_sync_enabled = False
    group.save(update_fields=["continuous_sync_enabled"])
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("pause_reason", "incident_status"),
    [(IncidentIMGroup.PauseReason.MANUAL, IncidentStatus.PROCESSING), (IncidentIMGroup.PauseReason.INCIDENT_CLOSED, IncidentStatus.CLOSED),],
)
def test_force_delivery_never_bypasses_pause_or_closed(group, channel, pause_reason, incident_status):
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = pause_reason
    group.save(update_fields=["status", "pause_reason"])
    group.incident.status = incident_status
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["status", "collaborators"])
    _map_user(channel, "bob")
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
        last_error_message="外部用户标识无效",
    )
    previous_updated_at = member.updated_at

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()
    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.FAILED
    assert member.last_error_code == "IM_MEMBER_INVALID"
    assert member.last_error_message == "外部用户标识无效"
    assert member.updated_at == previous_updated_at


@pytest.mark.django_db
def test_reconcile_does_not_enqueue_removed_unjoined_members(group):
    pending = IncidentIMMember.objects.create(
        group=group,
        username="former-pending",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former_pending",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    failed = IncidentIMMember.objects.create(
        group=group,
        username="former-failed",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former_failed",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )

    reconcile_incident_im_group(group.incident_id)

    pending.refresh_from_db()
    failed.refresh_from_db()
    assert pending.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert failed.sync_status == IncidentIMMember.SyncStatus.FAILED
    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_force_delivery_only_promotes_current_expected_failed_members(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    current = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
    )
    removed = IncidentIMMember.objects.create(
        group=group,
        username="former",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
    )

    reconcile_incident_im_group(group.incident_id, force_delivery=True)

    current.refresh_from_db()
    removed.refresh_from_db()
    assert current.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert removed.sync_status == IncidentIMMember.SyncStatus.FAILED
    assert removed.last_error_code == "IM_MEMBER_INVALID"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("pause_reason", "incident_status"),
    [(IncidentIMGroup.PauseReason.MANUAL, IncidentStatus.PROCESSING), (IncidentIMGroup.PauseReason.INCIDENT_CLOSED, IncidentStatus.CLOSED),],
)
def test_already_queued_add_delivery_stops_after_pause(group, pause_reason, incident_status):
    member = IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = pause_reason
    group.save(update_fields=["status", "pause_reason"])
    group.incident.status = incident_status
    group.incident.save(update_fields=["status"])

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        deliver_add_members(group.id)

    execute.assert_not_called()
    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.PENDING

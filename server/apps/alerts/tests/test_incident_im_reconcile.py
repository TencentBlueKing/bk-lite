import uuid
from types import SimpleNamespace
from unittest import mock

import pytest
from django.db.models import QuerySet

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.serializers.incident import IncidentModelSerializer
from apps.alerts.service.incident_im.delivery import deliver_add_members
from apps.alerts.service.incident_im.reconcile import pause_group_for_closed_incident, reconcile_incident_im_group, resume_group_for_reopened_incident
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tasks.tasks import reconcile_waiting_incident_im_groups
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationUserMapping, IntegrationInstance, User
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.fixture
def incident(db):
    return Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}", level="warning", title="持续同步测试", status=IncidentStatus.PROCESSING, operator=["alice"],
    )


@pytest.fixture
def channel(db):
    instance = IntegrationInstance.objects.create(name=f"feishu-{uuid.uuid4().hex}", provider_key="feishu", enabled=True, status="ready",)
    return IMNotificationChannel.objects.create(
        name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready", external_receive_field="open_id",
    )


@pytest.fixture
def group(incident, channel):
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="[Incident] 持续同步测试",
        external_chat_id="oc_test",
        status=IncidentIMGroup.Status.ACTIVE,
        current_stage=IncidentIMGroup.Stage.COMPLETED,
        continuous_sync_enabled=True,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


def _map_user(channel, username):
    user = User.objects.create(username=username, display_name=username.title(), email=f"{username}@example.com", password="test-password",)
    return IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="open_id",
        external_identity_value=f"identity-{username}",
        external_receive_key="open_id",
        external_snapshot={"open_id": f"ou_{username}"},
    )


def _incident_serializer(incident, data):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    with mock.patch(
        "apps.core.utils.serializers.get_permission_rules", return_value={"team": [], "instance": []},
    ):
        return IncidentModelSerializer(incident, data=data, partial=True, context={"request": request},)


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
    assert outbox.payload == {"group_id": str(group.id)}


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


@pytest.mark.django_db
def test_close_pause_and_reopen_resume_preserve_manual_pause(group):
    pause_group_for_closed_incident(group.incident_id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True

    group.incident.status = IncidentStatus.PROCESSING
    group.incident.save(update_fields=["status"])
    resume_group_for_reopened_incident(group.incident_id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert group.pause_reason == ""
    assert group.resume_after_reopen is False

    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.MANUAL
    group.resume_after_reopen = True
    group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
    resume_group_for_reopened_incident(group.incident_id)
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.MANUAL


@pytest.mark.django_db
def test_reopen_restores_partial_when_member_gap_exists_and_enqueues(group):
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    group.resume_after_reopen = True
    group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )

    resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    assert AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db
def test_reopen_ignores_removed_unjoined_history_when_restoring_active(group):
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    group.resume_after_reopen = False
    group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
    IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="former",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )

    resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE


@pytest.mark.django_db
def test_reopen_inflight_create_reconcile_continues_initial_members_when_continuous_sync_off(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    group.resume_after_reopen = True
    group.continuous_sync_enabled = False
    group.save(
        update_fields=["status", "pause_reason", "resume_after_reopen", "continuous_sync_enabled",]
    )

    resume_group_for_reopened_incident(group.incident_id)
    reconcile_outbox = AlertOutbox.objects.get(kind="incident_im_group.reconcile")
    assert reconcile_outbox.payload == {
        "incident_id": group.incident_id,
        "resume_create": True,
    }

    assert deliver_outbox_record(reconcile_outbox.id) is True
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()


@pytest.mark.django_db
def test_periodic_scan_is_fair_across_201_groups_and_isolates_failure(monkeypatch, incident, channel):
    groups = [
        IncidentIMGroup.objects.create(
            incident=Incident.objects.create(
                incident_id=f"INC-{index}-{uuid.uuid4().hex}", level="warning", title=f"scan-{index}", status=IncidentStatus.PROCESSING,
            ),
            channel=channel,
            provider_key="feishu",
            channel_name_snapshot=channel.name,
            member_id_type="open_id",
            group_name=f"scan-{index}",
            external_chat_id=f"oc_{index}",
            status=IncidentIMGroup.Status.ACTIVE,
            continuous_sync_enabled=True,
            idempotency_key=f"bklite-{uuid.uuid4().hex}",
        )
        for index in range(201)
    ]
    called = []

    def fake_reconcile(group_id):
        called.append(group_id)
        if len(called) == 1:
            raise RuntimeError("bad channel")

    monkeypatch.setattr(
        "apps.alerts.service.incident_im.reconcile.reconcile_incident_im_group_by_group_id", fake_reconcile,
    )

    first = reconcile_waiting_incident_im_groups()
    failed_group = groups[0]
    failed_group.refresh_from_db()
    second = reconcile_waiting_incident_im_groups()

    assert first == {"scheduled": 200, "failed": 1}
    assert failed_group.last_reconcile_attempt_at is not None
    assert failed_group.last_sync_at is None
    assert second["scheduled"] == 200
    assert {item.id for item in groups}.issubset(set(called))


@pytest.mark.django_db
def test_periodic_scan_isolates_reconcile_cursor_update_failure(monkeypatch, channel):
    groups = [
        IncidentIMGroup.objects.create(
            incident=Incident.objects.create(
                incident_id=f"INC-cursor-{index}-{uuid.uuid4().hex}", level="warning", title=f"cursor-{index}", status=IncidentStatus.PROCESSING,
            ),
            channel=channel,
            provider_key="feishu",
            channel_name_snapshot=channel.name,
            member_id_type="open_id",
            group_name=f"cursor-{index}",
            external_chat_id=f"oc_cursor_{index}",
            status=IncidentIMGroup.Status.ACTIVE,
            continuous_sync_enabled=True,
            idempotency_key=f"bklite-{uuid.uuid4().hex}",
        )
        for index in range(2)
    ]
    called = []
    real_update = QuerySet.update
    cursor_update_attempts = 0

    def fail_first_cursor_update(queryset, **kwargs):
        nonlocal cursor_update_attempts
        if queryset.model is IncidentIMGroup and ("last_sync_at" in kwargs or "last_reconcile_attempt_at" in kwargs):
            cursor_update_attempts += 1
            if cursor_update_attempts == 1:
                raise RuntimeError("cursor update failed")
        return real_update(queryset, **kwargs)

    monkeypatch.setattr(
        "apps.alerts.service.incident_im.reconcile.reconcile_incident_im_group_by_group_id", lambda group_id: called.append(group_id),
    )
    monkeypatch.setattr(QuerySet, "update", fail_first_cursor_update)

    result = reconcile_waiting_incident_im_groups()

    assert result == {"scheduled": 2, "failed": 1}
    assert set(called) == {group.id for group in groups}
    assert cursor_update_attempts == 2


@pytest.mark.django_db
def test_reconcile_group_lock_does_not_cover_external_provider_call(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])

    with mock.patch("apps.system_mgmt.services.im_group_service.IMGroupRuntimeService.execute") as execute:
        reconcile_incident_im_group(group.incident_id)

    execute.assert_not_called()


@pytest.mark.django_db
def test_incident_serializer_member_change_writes_reconcile_outbox_in_same_transaction(incident,):
    serializer = _incident_serializer(incident, {"collaborators": ["bob"]})
    assert serializer.is_valid(), serializer.errors

    updated = serializer.save()

    outbox = AlertOutbox.objects.get(kind="incident_im_group.reconcile")
    assert outbox.payload == {"incident_id": incident.pk}
    assert updated.updated_at.isoformat(timespec="microseconds") in outbox.idempotency_key


@pytest.mark.django_db
def test_incident_serializer_non_member_or_unchanged_member_update_has_no_reconcile_event(incident,):
    title_serializer = _incident_serializer(incident, {"title": "仅更新标题"})
    assert title_serializer.is_valid(), title_serializer.errors
    title_serializer.save()

    same_member_serializer = _incident_serializer(incident, {"collaborators": []})
    assert same_member_serializer.is_valid(), same_member_serializer.errors
    same_member_serializer.save()

    assert not AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db(transaction=True)
def test_incident_serializer_rolls_back_member_and_outbox_when_enqueue_fails(incident):
    from apps.alerts.service.incident_im import reconcile as reconcile_module

    real_enqueue = reconcile_module.enqueue_reconcile

    def enqueue_then_fail(updated_incident):
        real_enqueue(updated_incident)
        raise RuntimeError("transaction failed")

    serializer = _incident_serializer(incident, {"collaborators": ["bob"]})
    assert serializer.is_valid(), serializer.errors
    with mock.patch("apps.alerts.serializers.incident.enqueue_reconcile", side_effect=enqueue_then_fail,), pytest.raises(
        RuntimeError, match="transaction failed"
    ):
        serializer.save()

    incident.refresh_from_db()
    assert incident.collaborators == []
    assert not AlertOutbox.objects.filter(kind="incident_im_group.reconcile").exists()


@pytest.mark.django_db
def test_reconcile_outbox_dispatches_without_external_call(group, channel):
    _map_user(channel, "bob")
    group.incident.collaborators = ["bob"]
    group.incident.save(update_fields=["collaborators"])
    record = AlertOutbox.objects.create(
        kind="incident_im_group.reconcile", payload={"incident_id": group.incident_id}, idempotency_key=f"reconcile-{uuid.uuid4().hex}",
    )

    with mock.patch("apps.system_mgmt.services.im_group_service.IMGroupRuntimeService.execute") as execute:
        assert deliver_outbox_record(record.id) is True

    execute.assert_not_called()
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()

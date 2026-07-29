import uuid
from unittest import mock

import pytest
from django.db.models import QuerySet

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.reconcile import pause_group_for_closed_incident, reconcile_incident_im_group, resume_group_for_reopened_incident
from apps.alerts.service.outbox import deliver_outbox_record
from apps.alerts.tasks.tasks import reconcile_waiting_incident_im_groups
from apps.alerts.tests.incident_im_reconcile_fixtures import incident_serializer as _incident_serializer
from apps.alerts.tests.incident_im_reconcile_fixtures import map_user as _map_user

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_reconcile_fixtures"]


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

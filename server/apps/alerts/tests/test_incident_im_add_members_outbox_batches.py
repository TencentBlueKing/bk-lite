import threading
from datetime import timedelta
from unittest import mock

import pytest
from django.db import OperationalError, close_old_connections, connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.constants import OUTBOX_ADD_MEMBERS
from apps.alerts.service.outbox import _deliver_payload, deliver_outbox_record
from apps.alerts.tasks.tasks import deliver_alert_outbox
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_delivery_fixtures"]


def _add_pending_collaborators(group, count):
    usernames = [f"batch-user-{index:03d}" for index in range(count)]
    group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
    group.external_chat_id = "oc_batch"
    group.current_stage = IncidentIMGroup.Stage.ADDING_MEMBERS
    group.incident.collaborators = usernames
    group.incident.save(update_fields=["collaborators"])
    group.save(update_fields=["status", "external_chat_id", "current_stage"])
    return IncidentIMMember.objects.bulk_create(
        [
            IncidentIMMember(
                group=group,
                username=username,
                role=IncidentIMMember.Role.COLLABORATOR,
                external_id=f"ou_{index:03d}",
                external_id_type="open_id",
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            for index, username in enumerate(usernames)
        ]
    )


def _create_initial_add_outbox(group, suffix):
    return AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS, payload={"group_id": str(group.id)}, idempotency_key=f"incident-im-group:{group.id}:legacy-add:{suffix}",
    )


def _pending_add_outbox(group):
    return AlertOutbox.objects.get(kind=OUTBOX_ADD_MEMBERS, payload__group_id=str(group.id), status=AlertOutbox.Status.PENDING,)


@pytest.mark.parametrize(("member_count", "expected_calls"), [(51, 2), (101, 3)])
def test_each_add_outbox_delivers_at_most_one_batch_and_chains_remaining_members(group, member_count, expected_calls):
    _add_pending_collaborators(group, member_count)
    first = _create_initial_add_outbox(group, str(member_count))
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        current = first
        for completed_batches in range(1, expected_calls + 1):
            assert deliver_outbox_record(current.pk) is True
            assert execute.call_count == completed_batches
            assert all(len(call.kwargs["member_ids"]) <= 50 for call in execute.call_args_list)
            joined = group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count()
            assert joined == min(member_count, completed_batches * 50)
            if completed_batches < expected_calls:
                current = _pending_add_outbox(group)
                assert 1 <= len(current.payload["member_pks"]) <= 50
                assert current.idempotency_key.startswith(f"incident-im-group:{group.id}:add-members:")

    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 0


@pytest.mark.parametrize("terminal_change", ["pause", "close", "unlink"])
def test_chained_add_batch_respects_latest_group_lifecycle_before_call(group, terminal_change):
    _add_pending_collaborators(group, 51)
    first = _create_initial_add_outbox(group, terminal_change)
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        assert deliver_outbox_record(first.pk) is True
        second = _pending_add_outbox(group)
        if terminal_change == "pause":
            IncidentIMGroup.objects.filter(pk=group.pk).update(
                status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL,
            )
        elif terminal_change == "close":
            group.incident.status = IncidentStatus.CLOSED
            group.incident.save(update_fields=["status"])
        else:
            IncidentIMGroup.objects.filter(pk=group.pk).update(
                status=IncidentIMGroup.Status.UNLINKED, active_slot=None,
            )

        assert deliver_outbox_record(second.pk) is True

    assert execute.call_count == 1
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count() == 50
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 1


def test_add_batch_ack_loss_replay_does_not_repeat_committed_external_batch(group):
    members = _add_pending_collaborators(group, 51)
    first = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk for member in members[:50]],},
        idempotency_key=f"incident-im-group:{group.id}:ack-loss-frozen-batch",
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    def crash_after_local_commit(kind, payload, *, delivery_claim=None):
        _deliver_payload(kind, payload, delivery_claim=delivery_claim)
        raise RuntimeError("worker lost ACK after batch commit")

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute, mock.patch(
        "apps.alerts.service.outbox._deliver_payload", side_effect=crash_after_local_commit,
    ):
        with pytest.raises(RuntimeError, match="lost ACK"):
            deliver_outbox_record(first.pk)

    first.refresh_from_db()
    assert first.status == AlertOutbox.Status.PENDING
    assert execute.call_count == 1
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count() == 50

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as replay_execute:
        assert deliver_outbox_record(first.pk) is True

    replay_execute.assert_not_called()
    assert AlertOutbox.objects.filter(kind=OUTBOX_ADD_MEMBERS, payload__group_id=str(group.id), status=AlertOutbox.Status.PENDING,).count() == 1


def test_stale_claim_generation_cannot_reach_feishu_add_members(group):
    members = _add_pending_collaborators(group, 1)
    record = _create_initial_add_outbox(group, "stale-claim")
    record.status = AlertOutbox.Status.DELIVERING
    record.attempts = 2
    record.save(update_fields=["status", "attempts"])

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        _deliver_payload(
            record.kind, {"group_id": str(group.id), "member_pks": [members[0].pk]}, delivery_claim={"record_id": record.pk, "generation": 1},
        )

    execute.assert_not_called()
    members[0].refresh_from_db()
    assert members[0].sync_status == IncidentIMMember.SyncStatus.PENDING


def test_expired_group_lease_is_rejected_immediately_before_external_call(group):
    members = _add_pending_collaborators(group, 1)
    token = "expired-before-call"

    def acquire_expired(_group_id):
        IncidentIMGroup.objects.filter(pk=group.pk).update(
            delivery_lock_token=token,
            delivery_lock_expires_at=timezone.now() - timedelta(seconds=1),
        )
        return token

    with mock.patch(
        "apps.alerts.service.incident_im.delivery._acquire_group_delivery_lease",
        side_effect=acquire_expired,
    ), mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute"
    ) as execute:
        from apps.alerts.service.incident_im.delivery import deliver_add_members

        deliver_add_members(group.pk, member_pks=[members[0].pk])

    execute.assert_not_called()


def test_existing_new_add_outbox_prevents_create_retry_from_duplicating_batch(group):
    members = _add_pending_collaborators(group, 1)
    existing = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [members[0].pk],},
        idempotency_key=f"incident-im-group:{group.id}:existing-create-followup",
    )
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        deliver_create_group(group.pk)

    execute.assert_not_called()
    assert AlertOutbox.objects.filter(
        kind=OUTBOX_ADD_MEMBERS, payload__group_id=str(group.id)
    ).count() == 1
    existing.refresh_from_db()
    assert existing.status == AlertOutbox.Status.PENDING


def test_live_group_delivery_lease_blocks_second_add_outbox_call(group):
    _add_pending_collaborators(group, 1)
    first = _create_initial_add_outbox(group, "lease-holder")
    second = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS, payload={"group_id": str(group.id)}, idempotency_key=f"incident-im-group:{group.id}:lease-contender",
    )
    group.delivery_lock_token = "holder-token"
    group.delivery_lock_expires_at = timezone.now() + timedelta(seconds=75)
    group.save(update_fields=["delivery_lock_token", "delivery_lock_expires_at"])

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        with pytest.raises(RuntimeError, match="正在处理"):
            deliver_outbox_record(second.pk)

    execute.assert_not_called()
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == AlertOutbox.Status.PENDING
    assert second.status == AlertOutbox.Status.PENDING


def test_removed_member_in_frozen_batch_is_not_sent(group):
    members = _add_pending_collaborators(group, 2)
    group.incident.collaborators = [members[0].username]
    group.incident.save(update_fields=["collaborators"])
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    outbox = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk for member in members],},
        idempotency_key=f"incident-im-group:{group.id}:frozen-removed",
    )

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        assert deliver_outbox_record(outbox.pk) is True

    assert execute.call_args.kwargs["member_ids"] == [members[0].external_id]
    members[1].refresh_from_db()
    assert members[1].sync_status == IncidentIMMember.SyncStatus.PENDING


def test_retryable_add_failure_releases_group_lease_without_chaining(group):
    members = _add_pending_collaborators(group, 51)
    outbox = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk for member in members[:50]],},
        idempotency_key=f"incident-im-group:{group.id}:retryable-frozen-batch",
    )
    limited = CapabilityExecutionResult.failed_result("rate limited", code="provider.rate_limited", retryable=True)

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=limited,) as execute:
        with pytest.raises(RuntimeError, match="rate limited"):
            deliver_outbox_record(outbox.pk)

    assert execute.call_count == 1
    outbox.refresh_from_db()
    group.refresh_from_db()
    assert outbox.status == AlertOutbox.Status.PENDING
    assert outbox.attempts == 1
    assert group.delivery_lock_token == ""
    assert group.delivery_lock_expires_at is None
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 51
    assert AlertOutbox.objects.filter(kind=OUTBOX_ADD_MEMBERS, payload__group_id=str(group.id)).count() == 1


def test_permanent_add_failure_finishes_only_current_batch_and_chains_next(group):
    members = _add_pending_collaborators(group, 51)
    outbox = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk for member in members[:50]],},
        idempotency_key=f"incident-im-group:{group.id}:permanent-frozen-batch",
    )
    denied = CapabilityExecutionResult.failed_result("permission denied", code="provider.permission_denied")

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=denied,) as execute:
        assert deliver_outbox_record(outbox.pk) is True

    assert execute.call_count == 1
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.FAILED).count() == 50
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 1
    next_batch = _pending_add_outbox(group)
    assert next_batch.payload["member_pks"] == [members[-1].pk]


def test_next_batch_enqueue_failure_rolls_back_member_result_and_releases_lease(group):
    members = _add_pending_collaborators(group, 51)
    outbox = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk for member in members[:50]],},
        idempotency_key=f"incident-im-group:{group.id}:enqueue-rollback",
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox", side_effect=RuntimeError("outbox insert failed"),
    ):
        with pytest.raises(RuntimeError, match="outbox insert failed"):
            deliver_outbox_record(outbox.pk)

    outbox.refresh_from_db()
    group.refresh_from_db()
    assert outbox.status == AlertOutbox.Status.PENDING
    assert group.delivery_lock_token == ""
    assert group.delivery_lock_expires_at is None
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count() == 50
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 1


def test_expired_group_delivery_lease_can_be_reclaimed(group):
    _add_pending_collaborators(group, 1)
    outbox = _create_initial_add_outbox(group, "expired-lease")
    IncidentIMGroup.objects.filter(pk=group.pk).update(
        delivery_lock_token="crashed-worker", delivery_lock_expires_at=timezone.now() - timedelta(seconds=1),
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        assert deliver_outbox_record(outbox.pk) is True

    assert execute.call_count == 1
    group.refresh_from_db()
    assert group.delivery_lock_token == ""
    assert group.delivery_lock_expires_at is None


def test_removed_batch_consumed_empty_then_readded_enqueues_stable_resume_without_snapshot_change(group):
    from apps.alerts.service.incident_im.delivery import enqueue_add_members_batch

    member = _add_pending_collaborators(group, 1)[0]
    assert enqueue_add_members_batch(group) is True
    first = AlertOutbox.objects.get(kind=OUTBOX_ADD_MEMBERS)
    group.incident.collaborators = []
    group.incident.save(update_fields=["collaborators"])
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        assert deliver_outbox_record(first.pk) is True
    execute.assert_not_called()

    group.incident.collaborators = [member.username]
    group.incident.save(update_fields=["collaborators"])
    assert enqueue_add_members_batch(group) is True
    second = AlertOutbox.objects.filter(kind=OUTBOX_ADD_MEMBERS).exclude(pk=first.pk).get()
    assert second.idempotency_key == f"{first.idempotency_key}:resume:{first.pk}"

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        assert deliver_outbox_record(second.pk) is True
    execute.assert_called_once()
    member.refresh_from_db()
    assert member.sync_status == IncidentIMMember.SyncStatus.JOINED


def test_ongoing_member_sync_finishes_without_reusing_initial_summary_outbox(group):
    member = _add_pending_collaborators(group, 1)[0]
    group.last_sync_at = timezone.now() - timedelta(minutes=10)
    group.continuous_sync_enabled = False
    group.save(update_fields=["last_sync_at", "continuous_sync_enabled"])
    AlertOutbox.objects.create(
        kind="incident_im_group.send_summary",
        payload={"group_id": str(group.id)},
        idempotency_key=f"incident-im-group:{group.id}:send-summary",
        status=AlertOutbox.Status.DELIVERED,
    )
    add = AlertOutbox.objects.create(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group.id), "member_pks": [member.pk]},
        idempotency_key=f"incident-im-group:{group.id}:ongoing-add",
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,):
        assert deliver_outbox_record(add.pk) is True

    group.refresh_from_db()
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert AlertOutbox.objects.filter(kind="incident_im_group.send_summary", payload__group_id=str(group.id)).count() == 1


@pytest.mark.django_db(transaction=True)
def test_group_delivery_lease_cas_allows_only_one_concurrent_owner(group):
    from apps.alerts.service.incident_im.delivery import _acquire_group_delivery_lease

    _add_pending_collaborators(group, 1)
    barrier = threading.Barrier(2, timeout=5)
    tokens = []
    errors = []

    def acquire():
        close_old_connections()
        try:
            barrier.wait()
            tokens.append(_acquire_group_delivery_lease(group.pk))
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=acquire) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sum(bool(token) for token in tokens) == 1
    assert tokens.count("") == 1


def test_group_delivery_lease_cas_update_only_filters_group_table(group):
    from apps.alerts.service.incident_im.delivery import _acquire_group_delivery_lease

    with CaptureQueriesContext(connection) as queries:
        token = _acquire_group_delivery_lease(group.pk)

    assert token
    update_sql = next(query["sql"] for query in queries.captured_queries if query["sql"].lstrip().upper().startswith("UPDATE"))
    normalized = update_sql.upper()
    assert "SELECT" not in normalized
    assert "JOIN" not in normalized
    assert '"ALERTS_INCIDENT"' not in normalized


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("database is locked", ""),
        ("database table is locked: alerts_incidentimgroup", ""),
        ("database is busy", ""),
    ],
)
def test_group_delivery_lease_treats_only_sqlite_lock_contention_as_busy(group, message, expected):
    from apps.alerts.service.incident_im.delivery import _acquire_group_delivery_lease

    with mock.patch("django.db.models.query.QuerySet.update", side_effect=OperationalError(message)):
        assert _acquire_group_delivery_lease(group.pk) == expected


@pytest.mark.parametrize("message", ["no such table: alerts_incidentimgroup", "disk I/O error"])
def test_group_delivery_lease_reraises_non_lock_sqlite_operational_errors(group, message):
    from apps.alerts.service.incident_im.delivery import _acquire_group_delivery_lease

    with mock.patch("django.db.models.query.QuerySet.update", side_effect=OperationalError(message)):
        with pytest.raises(OperationalError, match=message):
            _acquire_group_delivery_lease(group.pk)


def test_delivery_task_limits_fit_group_and_outbox_leases():
    from apps.alerts.service.incident_im.delivery import GROUP_DELIVERY_LEASE_SECONDS
    from apps.alerts.service.outbox import OUTBOX_LEASE_TIMEOUT
    from apps.alerts.tasks.tasks import deliver_incident_im_add_members_outbox

    assert deliver_alert_outbox.soft_time_limit is None
    assert deliver_alert_outbox.time_limit is None
    assert deliver_incident_im_add_members_outbox.soft_time_limit == 45
    assert deliver_incident_im_add_members_outbox.time_limit == 60
    assert (
        deliver_incident_im_add_members_outbox.soft_time_limit
        < deliver_incident_im_add_members_outbox.time_limit
        < GROUP_DELIVERY_LEASE_SECONDS
        < OUTBOX_LEASE_TIMEOUT.total_seconds()
    )

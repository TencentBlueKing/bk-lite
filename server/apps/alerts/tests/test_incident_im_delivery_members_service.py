import uuid
from unittest import mock

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.outbox import deliver_outbox_record
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_delivery_fixtures"]


@pytest.mark.django_db
def test_add_members_marks_only_invalid_ids_failed(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    previous_updated_at = pending_members[0].updated_at
    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    result = CapabilityExecutionResult(
        success=True, partial_success=True, summary="partial", payload={"invalid_member_ids": [pending_members[1].external_id]},
    )
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_add_members(group.id)

    states = dict(group.members.values_list("username", "sync_status"))
    assert states == {
        pending_members[0].username: "joined",
        pending_members[1].username: "failed",
    }
    pending_members[0].refresh_from_db()
    pending_members[1].refresh_from_db()
    assert pending_members[0].updated_at > previous_updated_at
    assert pending_members[1].last_error_code == "IM_MEMBER_INVALID"
    assert pending_members[1].last_error_message == "外部用户标识无效"


@pytest.mark.django_db
def test_old_add_members_outbox_skips_pending_member_removed_from_incident(group):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    group.status = IncidentIMGroup.Status.ACTIVE
    group.external_chat_id = "oc_1"
    group.save(update_fields=["status", "external_chat_id"])
    current = IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    removed = IncidentIMMember.objects.create(
        group=group,
        username="former",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_former",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_add_members(group.id)

    assert execute.call_args.kwargs["member_ids"] == [current.external_id]
    removed.refresh_from_db()
    assert removed.sync_status == IncidentIMMember.SyncStatus.PENDING


@pytest.mark.django_db
def test_add_members_commits_one_successful_batch_and_enqueues_next_batch(group):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    group.incident.collaborators = [f"user-{index}" for index in range(51)]
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.bulk_create(
        [
            IncidentIMMember(
                group=group,
                username=f"user-{index}",
                role=IncidentIMMember.Role.COLLABORATOR,
                external_id=f"ou_{index}",
                external_id_type="open_id",
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            for index in range(51)
        ]
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=success,) as execute:
        deliver_add_members(group.id)

    assert execute.call_count == 1
    assert group.members.filter(sync_status="joined").count() == 50
    assert group.members.filter(sync_status="pending").count() == 1
    next_batch = AlertOutbox.objects.get(kind="incident_im_group.add_members", status=AlertOutbox.Status.PENDING)
    assert len(next_batch.payload["member_pks"]) == 1


@pytest.mark.django_db
def test_add_members_stops_before_second_batch_and_summary_when_paused_during_first_call(group,):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    group.incident.collaborators = [f"user-{index}" for index in range(51)]
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.bulk_create(
        [
            IncidentIMMember(
                group=group,
                username=f"user-{index}",
                role=IncidentIMMember.Role.COLLABORATOR,
                external_id=f"ou_{index}",
                external_id_type="open_id",
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            for index in range(51)
        ]
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    def pause_during_first_call(*_args, **_kwargs):
        IncidentIMGroup.objects.filter(pk=group.id).update(
            status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL,
        )
        return success

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=pause_during_first_call,
    ) as execute, mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox") as enqueue:
        deliver_add_members(group.id)

    assert execute.call_count == 1
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count() == 50
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 1
    enqueue.assert_not_called()


@pytest.mark.django_db
def test_add_members_reloads_current_expected_members_before_each_batch(group):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    usernames = [f"user-{index}" for index in range(51)]
    group.status = IncidentIMGroup.Status.ACTIVE
    group.external_chat_id = "oc_1"
    group.save(update_fields=["status", "external_chat_id"])
    group.incident.collaborators = usernames
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.bulk_create(
        [
            IncidentIMMember(
                group=group,
                username=username,
                role=IncidentIMMember.Role.COLLABORATOR,
                external_id=f"ou_{index}",
                external_id_type="open_id",
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            for index, username in enumerate(usernames)
        ]
    )
    success = CapabilityExecutionResult.success_result("added", payload={"invalid_member_ids": []})

    def remove_last_member_during_first_call(*_args, **_kwargs):
        group.incident.collaborators = usernames[:50]
        group.incident.save(update_fields=["collaborators"])
        return success

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=remove_last_member_during_first_call,
    ) as execute, mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox"):
        deliver_add_members(group.id)

    assert execute.call_count == 1
    removed = group.members.get(username=usernames[-1])
    assert removed.sync_status == IncidentIMMember.SyncStatus.PENDING


@pytest.mark.django_db
def test_group_not_found_marks_degraded_without_recreating(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    group.external_chat_id = "oc_deleted"
    group.save(update_fields=["external_chat_id"])
    missing = CapabilityExecutionResult.failed_result("group missing", code="provider.group_not_found")
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=missing,) as execute:
        deliver_add_members(group.id)

    group.refresh_from_db()
    assert group.status == "degraded"
    assert [call.kwargs["operation"] for call in execute.call_args_list] == ["add_members"]


@pytest.mark.django_db
def test_add_members_rechecks_unlinked_state_under_lock_before_external_call(group, pending_members):
    from apps.alerts.service.incident_im import delivery

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    real_lock_group = delivery._lock_group

    def unlink_before_lock(group_id):
        IncidentIMGroup.objects.filter(pk=group_id).update(
            status=IncidentIMGroup.Status.UNLINKED, active_slot=None,
        )
        return real_lock_group(group_id)

    with mock.patch("apps.alerts.service.incident_im.delivery._lock_group", side_effect=unlink_before_lock,), mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute"
    ) as execute:
        delivery.deliver_add_members(group.id)

    execute.assert_not_called()
    group.refresh_from_db()
    assert group.status == "unlinked"


@pytest.mark.django_db
@pytest.mark.django_db
def test_delivery_exhausted_moves_group_out_of_creating_state(group):
    from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

    handle_delivery_exhausted("incident_im_group.create", {"group_id": str(group.id)}, "timeout")
    group.refresh_from_db()
    assert group.status == "create_failed"

    group.external_chat_id = "oc_1"
    group.status = IncidentIMGroup.Status.CREATING
    group.save(update_fields=["external_chat_id", "status"])
    handle_delivery_exhausted("incident_im_group.add_members", {"group_id": str(group.id)}, "timeout")
    group.refresh_from_db()
    assert group.status == "active_partial"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "pause_reason", "external_chat_id"),
    [
        ("incident_im_group.create", IncidentIMGroup.PauseReason.MANUAL, ""),
        ("incident_im_group.create", IncidentIMGroup.PauseReason.INCIDENT_CLOSED, ""),
        ("incident_im_group.add_members", IncidentIMGroup.PauseReason.MANUAL, "oc_1"),
        ("incident_im_group.add_members", IncidentIMGroup.PauseReason.INCIDENT_CLOSED, "oc_1",),
        ("incident_im_group.send_summary", IncidentIMGroup.PauseReason.MANUAL, "oc_1"),
        ("incident_im_group.send_summary", IncidentIMGroup.PauseReason.INCIDENT_CLOSED, "oc_1",),
    ],
)
def test_delivery_exhausted_preserves_pause_and_outbox_failed_state(group, kind, pause_reason, external_chat_id):
    from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

    group.external_chat_id = external_chat_id
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
        kind=kind, payload={"group_id": str(group.id)}, idempotency_key=f"exhausted-paused-{uuid.uuid4().hex}", max_attempts=1,
    )

    with mock.patch(
        "apps.alerts.service.outbox._deliver_payload", side_effect=RuntimeError("provider timeout"),
    ):
        with pytest.raises(RuntimeError, match="provider timeout"):
            deliver_outbox_record(outbox.id)

    handle_delivery_exhausted(kind, outbox.payload, "provider timeout")
    group.refresh_from_db()
    outbox.refresh_from_db()
    assert outbox.status == AlertOutbox.Status.FAILED
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == pause_reason
    assert group.resume_after_reopen is True
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_error_code == "IM_DELIVERY_EXHAUSTED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("kind", "external_chat_id"),
    [("incident_im_group.create", ""), ("incident_im_group.add_members", "oc_1"), ("incident_im_group.send_summary", "oc_1"),],
)
def test_delivery_exhausted_is_noop_for_unlinked_history(group, kind, external_chat_id):
    from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

    group.external_chat_id = external_chat_id
    group.status = IncidentIMGroup.Status.UNLINKED
    group.active_slot = None
    group.current_stage = IncidentIMGroup.Stage.COMPLETED
    group.last_error_code = "IM_UNLINKED"
    group.last_error_message = "已解除绑定"
    group.save(
        update_fields=["external_chat_id", "status", "active_slot", "current_stage", "last_error_code", "last_error_message",]
    )

    handle_delivery_exhausted(kind, {"group_id": str(group.id)}, "provider timeout")

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.UNLINKED
    assert group.active_slot is None
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_error_code == "IM_UNLINKED"
    assert group.last_error_message == "已解除绑定"

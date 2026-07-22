import uuid
from unittest import mock

import pytest

from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.system_mgmt.models import IMNotificationChannel, IntegrationInstance
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.fixture
def group(db):
    incident = Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}",
        level="warning",
        title="数据库连接异常",
        operator=["alice"],
        collaborators=["bob"],
    )
    instance = IntegrationInstance.objects.create(
        name=f"feishu-{uuid.uuid4().hex}",
        provider_key="feishu",
        enabled=True,
        status="ready",
    )
    channel = IMNotificationChannel.objects.create(
        name=f"channel-{uuid.uuid4().hex}",
        integration_instance=instance,
        enabled=True,
        status="ready",
    )
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="[Incident] 数据库连接异常",
        external_owner_id="ou_alice",
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


@pytest.fixture
def pending_members(group):
    return [
        IncidentIMMember.objects.create(
            group=group,
            username=username,
            role=role,
            external_id=external_id,
            external_id_type="open_id",
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
            sync_status=IncidentIMMember.SyncStatus.PENDING,
        )
        for username, role, external_id in (
            ("alice", IncidentIMMember.Role.OPERATOR, "ou_alice"),
            ("bob", IncidentIMMember.Role.COLLABORATOR, "ou_bob"),
        )
    ]


@pytest.mark.django_db
def test_chat_id_is_saved_before_followup_events(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    result = CapabilityExecutionResult.success_result(
        "created", payload={"chat_id": "oc_1", "invalid_member_ids": []}
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox",
        side_effect=RuntimeError("worker crashed after ACK"),
    ):
        with pytest.raises(RuntimeError, match="worker crashed"):
            deliver_create_group(group.id)

    group.refresh_from_db()
    assert group.external_chat_id == "oc_1"
    assert set(group.members.values_list("sync_status", flat=True)) == {"joined"}


@pytest.mark.django_db
def test_create_retry_with_existing_chat_id_never_calls_create(group):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.external_chat_id = "oc_existing"
    group.save(update_fields=["external_chat_id"])
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute"
    ) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ) as enqueue:
        deliver_create_group(group.id)

    execute.assert_not_called()
    assert enqueue.call_args.args[0] == "incident_im_group.add_members"


@pytest.mark.django_db
def test_create_sends_owner_first_and_at_most_fifty_members(group):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

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
            for index in range(60)
        ]
    )
    IncidentIMMember.objects.create(
        group=group,
        username="owner",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_1"})
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ) as execute, mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox"):
        deliver_create_group(group.id)

    kwargs = execute.call_args.kwargs
    assert kwargs["operation"] == "create_group"
    assert kwargs["member_ids"][0] == "ou_alice"
    assert len(kwargs["member_ids"]) == 50


@pytest.mark.django_db
def test_create_marks_only_provider_invalid_initial_member_failed(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    result = CapabilityExecutionResult(
        success=True,
        partial_success=True,
        summary="created with invalid members",
        payload={
            "chat_id": "oc_1",
            "invalid_member_ids": [pending_members[1].external_id],
        },
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ), mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox"):
        deliver_create_group(group.id)

    pending_members[0].refresh_from_db()
    pending_members[1].refresh_from_db()
    assert pending_members[0].sync_status == "joined"
    assert pending_members[1].sync_status == "failed"
    assert pending_members[1].last_error_code == "IM_MEMBER_INVALID"
    assert pending_members[1].last_error_message == "外部用户标识无效"


@pytest.mark.django_db
def test_add_members_marks_only_invalid_ids_failed(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    previous_updated_at = pending_members[0].updated_at
    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    result = CapabilityExecutionResult(
        success=True,
        partial_success=True,
        summary="partial",
        payload={"invalid_member_ids": [pending_members[1].external_id]},
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ), mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox"):
        deliver_add_members(group.id)

    states = dict(group.members.values_list("username", "sync_status"))
    assert states == {pending_members[0].username: "joined", pending_members[1].username: "failed"}
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

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=success,
    ) as execute, mock.patch("apps.alerts.service.incident_im.delivery.enqueue_outbox"):
        deliver_add_members(group.id)

    assert execute.call_args.kwargs["member_ids"] == [current.external_id]
    removed.refresh_from_db()
    assert removed.sync_status == IncidentIMMember.SyncStatus.PENDING


@pytest.mark.django_db
def test_add_members_commits_successful_batch_before_next_batch_retry(group):
    from apps.alerts.service.incident_im.delivery import IncidentIMRetryableError, deliver_add_members

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
    limited = CapabilityExecutionResult.failed_result(
        "rate limited", code="provider.rate_limited", retryable=True
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        side_effect=[success, limited],
    ):
        with pytest.raises(IncidentIMRetryableError, match="rate limited"):
            deliver_add_members(group.id)

    assert group.members.filter(sync_status="joined").count() == 50
    assert group.members.filter(sync_status="pending").count() == 1


@pytest.mark.django_db
def test_add_members_stops_before_second_batch_and_summary_when_paused_during_first_call(group):
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
            status=IncidentIMGroup.Status.PAUSED,
            pause_reason=IncidentIMGroup.PauseReason.MANUAL,
        )
        return success

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        side_effect=pause_during_first_call,
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
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        side_effect=remove_last_member_during_first_call,
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
    missing = CapabilityExecutionResult.failed_result(
        "group missing", code="provider.group_not_found"
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=missing,
    ) as execute:
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
            status=IncidentIMGroup.Status.UNLINKED,
            active_slot=None,
        )
        return real_lock_group(group_id)

    with mock.patch(
        "apps.alerts.service.incident_im.delivery._lock_group",
        side_effect=unlink_before_lock,
    ), mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute"
    ) as execute:
        delivery.deliver_add_members(group.id)

    execute.assert_not_called()
    group.refresh_from_db()
    assert group.status == "unlinked"


@pytest.mark.django_db
def test_summary_failure_is_terminal_and_completes_as_partial(group):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    group.external_chat_id = "oc_1"
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["external_chat_id", "current_stage"])
    failed = CapabilityExecutionResult.failed_result(
        "message rejected", code="provider.permission_denied"
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=failed,
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
    limited = CapabilityExecutionResult.failed_result(
        "rate limited", code="provider.rate_limited", retryable=True
    )
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=limited,
    ):
        with pytest.raises(IncidentIMRetryableError, match="rate limited"):
            deliver_summary(group.id)


@pytest.mark.django_db
@pytest.mark.parametrize("gap_status", ["waiting", "pending", "adding", "failed"])
def test_summary_keeps_group_partial_for_every_non_joined_member_state(group, gap_status):
    from apps.alerts.service.incident_im.delivery import deliver_summary

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
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
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ):
        deliver_summary(group.id)

    group.refresh_from_db()
    assert group.status == "active_partial"


@pytest.mark.django_db
def test_summary_reuses_stable_provider_uuid_after_external_ack_before_local_confirmation_crash(group):
    from apps.alerts.service.incident_im import delivery

    group.external_chat_id = "oc_1"
    group.save(update_fields=["external_chat_id"])
    result = CapabilityExecutionResult.success_result("sent")
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery._lock_group",
        side_effect=RuntimeError("crash before local confirmation"),
    ):
        with pytest.raises(RuntimeError, match="crash before local confirmation"):
            delivery.deliver_summary(group.id)

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute",
        return_value=result,
    ) as retry_execute:
        delivery.deliver_summary(group.id)

    first_key = execute.call_args.kwargs["idempotency_key"]
    retry_key = retry_execute.call_args.kwargs["idempotency_key"]
    assert first_key == retry_key == f"bklite-summary-{group.id.hex}"


@pytest.mark.django_db
def test_delivery_exhausted_moves_group_out_of_creating_state(group):
    from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

    handle_delivery_exhausted(
        "incident_im_group.create", {"group_id": str(group.id)}, "timeout"
    )
    group.refresh_from_db()
    assert group.status == "create_failed"

    group.external_chat_id = "oc_1"
    group.status = IncidentIMGroup.Status.CREATING
    group.save(update_fields=["external_chat_id", "status"])
    handle_delivery_exhausted(
        "incident_im_group.add_members", {"group_id": str(group.id)}, "timeout"
    )
    group.refresh_from_db()
    assert group.status == "active_partial"

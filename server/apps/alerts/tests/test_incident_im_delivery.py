import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

import pytest
from django.db import close_old_connections, connections

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, Incident, IncidentIMGroup, IncidentIMMember, OperatorLog
from apps.alerts.service.incident_im.reconcile import pause_group_for_closed_incident, reconcile_incident_im_group, resume_group_for_reopened_incident
from apps.alerts.service.outbox import deliver_outbox_record
from apps.system_mgmt.models import IMNotificationChannel, IntegrationInstance
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


@pytest.fixture
def group(db):
    incident = Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}", level="warning", title="数据库连接异常", operator=["alice"], collaborators=["bob"],
    )
    instance = IntegrationInstance.objects.create(name=f"feishu-{uuid.uuid4().hex}", provider_key="feishu", enabled=True, status="ready",)
    channel = IMNotificationChannel.objects.create(name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready",)
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

    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_1", "invalid_member_ids": []})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox", side_effect=RuntimeError("worker crashed after ACK"),
    ):
        with pytest.raises(RuntimeError, match="worker crashed"):
            deliver_create_group(group.id)

    group.refresh_from_db()
    assert group.external_chat_id == "oc_1"
    assert set(group.members.values_list("sync_status", flat=True)) == {"joined"}


@pytest.mark.django_db
def test_create_result_audit_uses_counts_without_external_ids(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.created_by = "alice"
    group.save(update_fields=["created_by"])
    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_secret", "invalid_member_ids": ["ou_bob"]},)

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,
    ):
        deliver_create_group(group.id)

    assert not OperatorLog.objects.filter(target_id=group.incident.incident_id, overview__contains="创建飞书群最终结果",).exists()


@pytest.mark.django_db
def test_create_failure_is_audited_without_provider_payload(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.created_by = "alice"
    group.save(update_fields=["created_by"])
    result = CapabilityExecutionResult.failed_result("provider secret response", code="provider.permission_denied",)

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,
    ):
        deliver_create_group(group.id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.CREATE_FAILED
    log = OperatorLog.objects.filter(target_id=group.incident.incident_id, overview__contains="创建飞书群最终结果",).latest("id")
    assert "失败" in log.overview
    assert "provider secret response" not in log.overview


@pytest.mark.django_db
def test_add_members_result_audit_uses_counts_without_external_ids(group):
    from apps.alerts.service.incident_im.delivery import deliver_add_members

    group.created_by = "alice"
    group.external_chat_id = "oc_secret"
    group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
    group.save(update_fields=["created_by", "external_chat_id", "status"])
    IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="bob",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_bob",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    result = CapabilityExecutionResult.success_result("partial", payload={"invalid_member_ids": ["ou_bob"]},)

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,
    ):
        deliver_add_members(group.id)

    log = OperatorLog.objects.filter(target_id=group.incident.incident_id, overview__contains="补拉飞书群成员结果",).latest("id")
    assert "成功 1 人" in log.overview
    assert "失败 1 人" in log.overview
    assert "oc_secret" not in log.overview
    assert "ou_bob" not in log.overview


@pytest.mark.django_db
def test_create_final_audit_waits_for_summary_and_has_structured_safe_context(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group, deliver_summary

    group.created_by = "alice"
    group.save(update_fields=["created_by"])
    create_result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_secret", "invalid_member_ids": []},)
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=create_result,
    ):
        deliver_create_group(group.id)

    assert not OperatorLog.objects.filter(target_id=group.incident.incident_id, overview__contains="创建飞书群最终结果",).exists()

    summary_result = CapabilityExecutionResult.success_result("sent")
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=summary_result,
    ):
        deliver_summary(group.id)

    log = OperatorLog.objects.get(target_id=group.incident.incident_id, overview__contains="创建飞书群最终结果",)
    assert '"channel_name_snapshot"' in log.overview
    assert '"binding_id"' in log.overview
    assert '"member_result"' in log.overview
    assert "oc_secret" not in log.overview
    assert "ou_alice" not in log.overview


@pytest.mark.django_db
def test_summary_exhaustion_audit_is_not_mislabeled_as_member_delivery(group):
    from apps.alerts.service.incident_im.delivery import handle_delivery_exhausted

    group.external_chat_id = "oc_secret"
    group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
    group.save(update_fields=["external_chat_id", "status"])

    handle_delivery_exhausted(
        "incident_im_group.send_summary", {"group_id": str(group.id)}, "timeout",
    )

    log = OperatorLog.objects.filter(target_id=group.incident.incident_id).latest("id")
    assert "摘要发送结果" in log.overview
    assert "补拉飞书群成员结果" not in log.overview
    assert "oc_secret" not in log.overview


@pytest.mark.django_db
def test_create_retry_with_existing_chat_id_never_calls_create(group):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.external_chat_id = "oc_existing"
    group.save(update_fields=["external_chat_id"])
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ) as enqueue:
        deliver_create_group(group.id)

    execute.assert_not_called()
    assert enqueue.call_args.args[0] == "incident_im_group.add_members"


@pytest.mark.django_db
def test_create_sends_owner_first_and_at_most_fifty_members(group):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.incident.collaborators = [f"user-{index}" for index in range(60)]
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
            for index in range(60)
        ]
    )
    IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_1"})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_create_group(group.id)

    kwargs = execute.call_args.kwargs
    assert kwargs["operation"] == "create_group"
    assert kwargs["member_ids"][0] == "ou_alice"
    assert len(kwargs["member_ids"]) == 50


@pytest.mark.django_db
def test_create_group_skips_member_removed_after_outbox_was_queued(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    group.incident.collaborators = []
    group.incident.save(update_fields=["collaborators"])
    result = CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_1"})
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,) as execute, mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
        deliver_create_group(group.id)

    assert execute.call_args.kwargs["member_ids"] == [pending_members[0].external_id]
    pending_members[1].refresh_from_db()
    assert pending_members[1].sync_status == IncidentIMMember.SyncStatus.PENDING


@pytest.mark.django_db
def test_create_group_fails_closed_when_snapshotted_owner_is_no_longer_current_operator(group, pending_members):
    group.incident.operator = ["bob"]
    group.incident.collaborators = []
    group.incident.save(update_fields=["operator", "collaborators"])
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}, idempotency_key=f"create-owner-mismatch-{uuid.uuid4().hex}",
    )
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        assert deliver_outbox_record(outbox.id) is True

    execute.assert_not_called()
    group.refresh_from_db()
    outbox.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.CREATE_FAILED
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_error_code == "IM_OWNER_NOT_CURRENT_OPERATOR"
    assert group.last_error_message == "建群负责人已不再是当前 Incident 负责人"
    assert outbox.status == AlertOutbox.Status.DELIVERED


@pytest.mark.django_db
def test_create_outbox_closed_before_delivery_pauses_without_provider_and_reopen_requeues_create(group, pending_members):
    group.incident.status = IncidentStatus.CLOSED
    group.incident.save(update_fields=["status"])
    pause_group_for_closed_incident(group.incident_id)
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}, idempotency_key=f"create-before-close-{uuid.uuid4().hex}",
    )

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute") as execute:
        assert deliver_outbox_record(outbox.id) is True

    execute.assert_not_called()
    group.refresh_from_db()
    outbox.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True
    assert outbox.status == AlertOutbox.Status.DELIVERED

    group.incident.status = IncidentStatus.PROCESSING
    group.incident.save(update_fields=["status", "updated_at"])
    resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.current_stage == IncidentIMGroup.Stage.QUEUED
    assert group.pause_reason == ""
    assert (
        AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,)
        .exclude(pk=outbox.pk)
        .count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_create_ack_after_close_persists_ack_but_stays_paused_and_reopen_reconciles(group, pending_members):
    if connections["default"].vendor != "sqlite":
        pytest.skip("当前 Barrier 合同使用 SQLite 独立连接验证")
    collaborators = [f"user-{index}" for index in range(50)]
    group.incident.collaborators = collaborators
    group.incident.save(update_fields=["collaborators"])
    IncidentIMMember.objects.bulk_create(
        [
            IncidentIMMember(
                group=group,
                username=username,
                role=IncidentIMMember.Role.COLLABORATOR,
                external_id=f"ou_{username}",
                external_id_type="open_id",
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            for username in collaborators
        ]
    )
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}, idempotency_key=f"create-inflight-close-{uuid.uuid4().hex}",
    )
    barrier = Barrier(2)

    def provider_ack_after_close(*args, **kwargs):
        barrier.wait(timeout=10)
        barrier.wait(timeout=10)
        return CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_race", "invalid_member_ids": []})

    def deliver_from_independent_connection():
        close_old_connections()
        try:
            return deliver_outbox_record(outbox.id)
        finally:
            connections.close_all()

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=provider_ack_after_close,
    ):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(deliver_from_independent_connection)
            try:
                barrier.wait(timeout=10)
                group.incident.status = IncidentStatus.CLOSED
                group.incident.save(update_fields=["status"])
                pause_group_for_closed_incident(group.incident_id)
                barrier.wait(timeout=10)
                assert future.result(timeout=20) is True
            finally:
                barrier.abort()
                if not future.done():
                    future.cancel()

    group.refresh_from_db()
    outbox.refresh_from_db()
    assert group.external_chat_id == "oc_race"
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.resume_after_reopen is True
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.JOINED).count() == 50
    assert group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).count() == 2
    assert not AlertOutbox.objects.filter(kind__in=["incident_im_group.add_members", "incident_im_group.send_summary"]).exists()
    assert outbox.status == AlertOutbox.Status.DELIVERED

    group.incident.status = IncidentStatus.PROCESSING
    group.incident.save(update_fields=["status", "updated_at"])
    resume_group_for_reopened_incident(group.incident_id)

    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    assert group.pause_reason == ""
    assert AlertOutbox.objects.filter(kind="incident_im_group.reconcile", status=AlertOutbox.Status.PENDING).count() == 1


@pytest.mark.django_db
def test_create_ack_after_close_with_all_initial_members_requeues_summary_on_reopen(group, pending_members):
    outbox = AlertOutbox.objects.create(
        kind="incident_im_group.create", payload={"group_id": str(group.id)}, idempotency_key=f"create-inflight-close-all-joined-{uuid.uuid4().hex}",
    )

    def provider_ack_after_close(*_args, **_kwargs):
        group.incident.status = IncidentStatus.CLOSED
        group.incident.save(update_fields=["status"])
        pause_group_for_closed_incident(group.incident_id)
        return CapabilityExecutionResult.success_result("created", payload={"chat_id": "oc_all_joined", "invalid_member_ids": []},)

    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=provider_ack_after_close,) as execute:
        assert deliver_outbox_record(outbox.id) is True

    assert execute.call_count == 1
    group.refresh_from_db()
    assert group.external_chat_id == "oc_all_joined"
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    assert group.current_stage == IncidentIMGroup.Stage.ADDING_MEMBERS
    assert set(group.members.values_list("sync_status", flat=True)) == {IncidentIMMember.SyncStatus.JOINED}

    group.incident.status = IncidentStatus.PROCESSING
    group.incident.save(update_fields=["status", "updated_at"])
    resume_group_for_reopened_incident(group.incident_id)
    reconcile_outbox = AlertOutbox.objects.get(kind="incident_im_group.reconcile", status=AlertOutbox.Status.PENDING,)
    assert deliver_outbox_record(reconcile_outbox.id) is True

    reconcile_incident_im_group(group.incident_id, resume_create=True)
    resume_group_for_reopened_incident(group.incident_id)
    summaries = AlertOutbox.objects.filter(
        kind="incident_im_group.send_summary", payload={"group_id": str(group.id)}, status=AlertOutbox.Status.PENDING,
    )
    assert summaries.count() == 1

    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=CapabilityExecutionResult.success_result("sent"),
    ) as execute:
        assert deliver_outbox_record(summaries.get().id) is True

    assert execute.call_args.kwargs["idempotency_key"] == f"bklite-summary-{group.id.hex}"
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.ACTIVE
    assert group.current_stage == IncidentIMGroup.Stage.COMPLETED
    assert group.last_sync_at is not None


@pytest.mark.django_db
def test_create_marks_only_provider_invalid_initial_member_failed(group, pending_members):
    from apps.alerts.service.incident_im.delivery import deliver_create_group

    result = CapabilityExecutionResult(
        success=True,
        partial_success=True,
        summary="created with invalid members",
        payload={"chat_id": "oc_1", "invalid_member_ids": [pending_members[1].external_id]},
    )
    with mock.patch("apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", return_value=result,), mock.patch(
        "apps.alerts.service.incident_im.delivery.enqueue_outbox"
    ):
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
    limited = CapabilityExecutionResult.failed_result("rate limited", code="provider.rate_limited", retryable=True)
    with mock.patch(
        "apps.alerts.service.incident_im.delivery.IMGroupRuntimeService.execute", side_effect=[success, limited],
    ):
        with pytest.raises(IncidentIMRetryableError, match="rate limited"):
            deliver_add_members(group.id)

    assert group.members.filter(sync_status="joined").count() == 50
    assert group.members.filter(sync_status="pending").count() == 1


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

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

import pytest
from django.db import close_old_connections, connections
from django.test import override_settings

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember, OperatorLog
from apps.alerts.service.incident_im.reconcile import pause_group_for_closed_incident, reconcile_incident_im_group, resume_group_for_reopened_incident
from apps.alerts.service.outbox import deliver_outbox_record
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_delivery_fixtures"]


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


@override_settings(WEB_BASE_URL="https://bklite.example.com/console/")
def test_incident_summary_contains_complete_context_and_encoded_detail_url(group):
    from apps.alerts.service.incident_im.delivery import _build_incident_summary

    group.incident.incident_id = "INC /?#中文"
    group.incident.title = "数据库连接异常"
    group.incident.level = "critical"
    group.incident.status = "processing"
    group.incident.operator = ["alice", "bob"]
    group.incident.save(update_fields=["incident_id", "title", "level", "status", "operator"])

    summary = _build_incident_summary(group)

    assert summary.splitlines() == [
        "Incident 协作群已建立",
        "",
        "编号：INC /?#中文",
        "标题：数据库连接异常",
        "级别：critical",
        "状态：processing",
        "负责人：alice、bob",
        ("详情：https://bklite.example.com/console/alarm/incidents/detail" f"?id={group.incident.pk}&incident_id=INC+%2F%3F%23%E4%B8%AD%E6%96%87"),
    ]


@pytest.mark.django_db
@override_settings(WEB_BASE_URL="")
def test_incident_summary_uses_relative_detail_url_without_localhost(group):
    from apps.alerts.service.incident_im.delivery import _build_incident_summary

    group.incident.operator = []
    group.incident.save(update_fields=["operator"])

    summary = _build_incident_summary(group)

    assert (f"详情：/alarm/incidents/detail?id={group.incident.pk}" f"&incident_id={group.incident.incident_id}") in summary
    assert "负责人：无" in summary
    assert "localhost" not in summary


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

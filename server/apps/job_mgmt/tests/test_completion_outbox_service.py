"""作业完成 outbox 的恢复、租约和幂等投递测试。"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.db import transaction
from django.utils import timezone
from nats.js.errors import ObjectNotFoundError

from apps.job_mgmt.constants import CallbackType, ExecutionStatus, JobType, TargetSource
from apps.job_mgmt.models import JobCompletionOutbox, JobExecution
from apps.job_mgmt.services.completion_outbox_service import (
    _claim_delivery,
    _mark_delivery_succeeded,
    deliver_outbox_record,
    due_outbox_ids,
    enqueue_terminal_effects,
)


def _terminal_execution(callback_type=CallbackType.BOTH):
    return JobExecution.objects.create(
        name="outbox-job",
        job_type=JobType.SCRIPT,
        status=ExecutionStatus.SUCCESS,
        target_source=TargetSource.MANUAL,
        target_list=[{"target_id": "target-1", "name": "host-1", "ip": "10.0.0.1"}],
        execution_results=[{"target_key": "target-1", "status": ExecutionStatus.SUCCESS}],
        total_count=1,
        success_count=1,
        callback_type=callback_type,
        callback_url="https://example.com/callback",
        callback_subject="bklite.alert_job_result",
        finished_at=timezone.now(),
        team=[1],
        created_by="testuser",
        updated_by="testuser",
    )


@pytest.mark.django_db(transaction=True)
def test_terminal_and_effect_intents_rollback_together():
    execution = _terminal_execution()
    execution.status = ExecutionStatus.RUNNING
    execution.save(update_fields=["status", "updated_at"])

    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            execution.status = ExecutionStatus.SUCCESS
            execution.save(update_fields=["status", "updated_at"])
            enqueue_terminal_effects(execution)
            raise RuntimeError("rollback")

    execution.refresh_from_db()
    assert execution.status == ExecutionStatus.RUNNING
    assert not JobCompletionOutbox.objects.filter(execution_id=execution.id).exists()


@pytest.mark.django_db
def test_each_channel_and_target_has_independent_stable_delivery_id():
    execution = _terminal_execution()
    with transaction.atomic():
        first = enqueue_terminal_effects(execution)
    with transaction.atomic():
        second = enqueue_terminal_effects(execution)

    assert len(first) == 3
    assert [record.pk for record in first] == [record.pk for record in second]
    assert JobCompletionOutbox.objects.filter(execution_id=execution.id).count() == 3
    assert len(set(JobCompletionOutbox.objects.values_list("idempotency_key", flat=True))) == 3

    web = JobCompletionOutbox.objects.get(kind=JobCompletionOutbox.Kind.WEB_CALLBACK)
    nats = JobCompletionOutbox.objects.get(kind=JobCompletionOutbox.Kind.NATS_CALLBACK)
    assert web.payload["delivery_id"] == web.idempotency_key
    assert nats.payload["callback_payload"]["delivery_id"] == nats.idempotency_key


@pytest.mark.django_db(transaction=True)
def test_failed_delivery_retries_with_same_payload_and_delivery_id():
    execution = _terminal_execution(callback_type=CallbackType.NATS)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        with transaction.atomic():
            enqueue_terminal_effects(execution)
    record = JobCompletionOutbox.objects.get(kind=JobCompletionOutbox.Kind.NATS_CALLBACK)
    original_payload = record.payload

    with patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_job_result_to_subject",
        side_effect=RuntimeError("nats down"),
    ) as publish:
        with pytest.raises(RuntimeError, match="nats down"):
            deliver_outbox_record(record.pk)
    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.PENDING
    assert record.attempts == 1
    assert record.payload == original_payload
    first_payload = publish.call_args.args[1]

    JobCompletionOutbox.objects.filter(pk=record.pk).update(next_retry_at=timezone.now())
    with patch("apps.job_mgmt.services.completion_outbox_service.publish_job_result_to_subject") as publish:
        assert deliver_outbox_record(record.pk) is True
    assert publish.call_args.args[1] == first_payload
    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.DELIVERED
    assert record.attempts == 2


@pytest.mark.django_db(transaction=True)
def test_exhausted_retry_cycle_cools_down_then_recovers_automatically():
    record = JobCompletionOutbox.objects.create(
        execution_id=1,
        kind=JobCompletionOutbox.Kind.NATS_CALLBACK,
        payload={
            "subject": "bklite.alert_job_result",
            "callback_payload": {"task_id": 1, "delivery_id": "cycle-retry"},
            "delivery_id": "cycle-retry",
        },
        idempotency_key="cycle-retry",
        max_attempts=1,
    )

    with patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_job_result_to_subject",
        side_effect=RuntimeError("nats down"),
    ):
        with pytest.raises(RuntimeError, match="nats down"):
            deliver_outbox_record(record.pk)
    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.FAILED
    assert record.next_retry_at > timezone.now()

    JobCompletionOutbox.objects.filter(pk=record.pk).update(next_retry_at=timezone.now())
    assert due_outbox_ids() == [record.pk]
    with patch("apps.job_mgmt.services.completion_outbox_service.publish_job_result_to_subject"):
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.DELIVERED
    assert record.attempts == 1


@pytest.mark.django_db(transaction=True)
def test_both_channels_progress_independently_when_nats_fails():
    execution = _terminal_execution(callback_type=CallbackType.BOTH)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        with transaction.atomic():
            enqueue_terminal_effects(execution)
    web = JobCompletionOutbox.objects.get(
        execution_id=execution.id,
        kind=JobCompletionOutbox.Kind.WEB_CALLBACK,
    )
    nats = JobCompletionOutbox.objects.get(
        execution_id=execution.id,
        kind=JobCompletionOutbox.Kind.NATS_CALLBACK,
    )

    with patch("apps.job_mgmt.services.completion_outbox_service.SSRFValidator.validate_callback"), patch(
        "apps.job_mgmt.services.completion_outbox_service.safe_post",
        return_value=MagicMock(status_code=200),
    ):
        assert deliver_outbox_record(web.pk) is True
    with patch(
        "apps.job_mgmt.services.completion_outbox_service.publish_job_result_to_subject",
        side_effect=RuntimeError("nats down"),
    ):
        with pytest.raises(RuntimeError, match="nats down"):
            deliver_outbox_record(nats.pk)

    web.refresh_from_db()
    nats.refresh_from_db()
    assert web.status == JobCompletionOutbox.Status.DELIVERED
    assert nats.status == JobCompletionOutbox.Status.PENDING


@pytest.mark.django_db
def test_expired_delivery_lease_is_recovered_but_live_lease_is_not():
    expired = JobCompletionOutbox.objects.create(
        execution_id=1,
        kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        payload={},
        idempotency_key="expired",
        status=JobCompletionOutbox.Status.DELIVERING,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
    )
    JobCompletionOutbox.objects.create(
        execution_id=2,
        kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        payload={},
        idempotency_key="live",
        status=JobCompletionOutbox.Status.DELIVERING,
        lease_expires_at=timezone.now() + timedelta(minutes=5),
    )

    assert due_outbox_ids() == [expired.pk]


@pytest.mark.django_db(transaction=True)
def test_expired_worker_token_cannot_overwrite_new_delivery_owner():
    record = JobCompletionOutbox.objects.create(
        execution_id=1,
        kind=JobCompletionOutbox.Kind.DONE_SENTINEL,
        payload={"execution_id": 1, "target_key": "t1", "status": ExecutionStatus.SUCCESS},
        idempotency_key="lease-fencing",
    )
    first_token = _claim_delivery(record.pk)[2]
    JobCompletionOutbox.objects.filter(pk=record.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))

    second_token = _claim_delivery(record.pk)[2]
    assert second_token != first_token
    assert _mark_delivery_succeeded(record.pk, first_token) is False

    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.DELIVERING
    assert record.lease_token == second_token
    assert _mark_delivery_succeeded(record.pk, second_token) is True


@pytest.mark.django_db(transaction=True)
def test_web_delivery_signs_additive_delivery_id():
    execution = _terminal_execution(callback_type=CallbackType.WEB)
    with patch("apps.job_mgmt.services.completion_outbox_service._schedule_deliveries"):
        with transaction.atomic():
            enqueue_terminal_effects(execution)
    record = JobCompletionOutbox.objects.get(kind=JobCompletionOutbox.Kind.WEB_CALLBACK)
    response = MagicMock(status_code=204)

    with patch("apps.job_mgmt.services.completion_outbox_service.SSRFValidator.validate_callback"), patch(
        "apps.job_mgmt.services.completion_outbox_service.get_signed_headers",
        return_value={"X-Test": "signed"},
    ) as signed_headers, patch(
        "apps.job_mgmt.services.completion_outbox_service.safe_post",
        return_value=response,
    ) as safe_post:
        assert deliver_outbox_record(record.pk) is True

    callback_payload = safe_post.call_args.kwargs["json"]
    assert callback_payload["delivery_id"] == record.idempotency_key
    signed_headers.assert_called_once_with(callback_payload)
    assert safe_post.call_args.kwargs["headers"] == {"X-Test": "signed"}


@pytest.mark.django_db
def test_cleanup_replay_treats_already_deleted_object_as_success():
    record = JobCompletionOutbox.objects.create(
        execution_id=1,
        kind=JobCompletionOutbox.Kind.PLAYBOOK_CLEANUP,
        payload={"file_key": "job-playbooks/1/demo.yml", "delivery_id": "cleanup-1"},
        idempotency_key="cleanup-1",
    )

    with patch(
        "apps.job_mgmt.services.completion_outbox_service.delete_s3_file",
        side_effect=ObjectNotFoundError,
    ):
        assert deliver_outbox_record(record.pk) is True

    record.refresh_from_db()
    assert record.status == JobCompletionOutbox.Status.DELIVERED

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils.timezone import now

from apps.cmdb.models.ipam_models import IPAMReconcileRun, IPAMReconcileRunStatus
from apps.cmdb.services.ipam_reconcile_job import IPAMReconcileJob


pytestmark = pytest.mark.django_db


def test_enqueue_reuses_active_run_and_dispatches_only_pending(monkeypatch):
    dispatched = []
    monkeypatch.setattr(IPAMReconcileJob, "_dispatch", staticmethod(lambda run_id: dispatched.append(run_id)))

    first = IPAMReconcileJob.enqueue(trigger="manual")
    second = IPAMReconcileJob.enqueue(trigger="scheduled")

    assert second.run.id == first.run.id
    assert first.reused is False
    assert second.reused is True
    assert dispatched == [first.run.run_id, first.run.run_id]
    assert IPAMReconcileRun.objects.filter(status=IPAMReconcileRunStatus.PENDING).count() == 1


def test_enqueue_keeps_pending_run_when_broker_dispatch_fails(monkeypatch, caplog):
    secret_error = "amqp://user:secret-value@broker unavailable"
    monkeypatch.setattr(
        IPAMReconcileJob,
        "_dispatch",
        staticmethod(lambda run_id: (_ for _ in ()).throw(RuntimeError(secret_error))),
    )

    result = IPAMReconcileJob.enqueue(trigger="manual")

    result.run.refresh_from_db()
    assert result.run.status == IPAMReconcileRunStatus.PENDING
    assert "RuntimeError" in result.run.last_error
    assert secret_error not in result.run.last_error
    assert secret_error not in caplog.text


def test_database_unique_active_scope_is_final_singleton_guard():
    IPAMReconcileRun.objects.create(trigger="manual")

    with pytest.raises(IntegrityError), transaction.atomic():
        IPAMReconcileRun.objects.create(trigger="scheduled")


def test_worker_claims_once_and_records_success(monkeypatch):
    result = IPAMReconcileJob.enqueue(trigger="manual", dispatch=False)
    monkeypatch.setattr(
        "apps.cmdb.services.ipam_reconcile.run_reconciliation",
        lambda: {"created": 2, "updated": 1},
    )

    output = IPAMReconcileJob.execute(result.run.run_id, owner_token="worker-1")
    duplicate = IPAMReconcileJob.execute(result.run.run_id, owner_token="worker-2")

    result.run.refresh_from_db()
    assert output == {"created": 2, "updated": 1}
    assert duplicate == {"created": 2, "updated": 1}
    assert result.run.status == IPAMReconcileRunStatus.SUCCESS
    assert result.run.stats == output
    assert result.run.started_at is not None
    assert result.run.finished_at is not None


def test_worker_failure_records_safe_error_and_propagates(monkeypatch):
    result = IPAMReconcileJob.enqueue(trigger="scheduled", dispatch=False)
    monkeypatch.setattr(
        "apps.cmdb.services.ipam_reconcile.run_reconciliation",
        lambda: (_ for _ in ()).throw(RuntimeError("graph credentials secret-value")),
    )

    with pytest.raises(RuntimeError, match="graph credentials"):
        IPAMReconcileJob.execute(result.run.run_id, owner_token="worker-1")

    result.run.refresh_from_db()
    assert result.run.status == IPAMReconcileRunStatus.ERROR
    assert "RuntimeError" in result.run.last_error
    assert "secret-value" not in result.run.last_error
    assert result.run.finished_at is not None


def test_expired_owner_can_be_replaced_but_cannot_finish_new_generation(monkeypatch):
    result = IPAMReconcileJob.enqueue(trigger="manual", dispatch=False)
    stale_time = now() - timedelta(minutes=1)
    IPAMReconcileRun.objects.filter(id=result.run.id).update(
        status=IPAMReconcileRunStatus.RUNNING,
        owner_token="old-owner",
        lease_expires_at=stale_time,
        started_at=stale_time,
    )

    claimed = IPAMReconcileJob.claim(result.run.run_id, owner_token="new-owner", lease_seconds=300)
    old_finished = IPAMReconcileJob.finish_success(
        result.run.run_id,
        owner_token="old-owner",
        stats={"created": 99},
    )

    result.run.refresh_from_db()
    assert claimed is True
    assert old_finished is False
    assert result.run.status == IPAMReconcileRunStatus.RUNNING
    assert result.run.owner_token == "new-owner"
    assert result.run.stats == {}

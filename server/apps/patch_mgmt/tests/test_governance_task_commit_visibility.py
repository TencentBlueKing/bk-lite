"""治理任务提交可见性：事务提交后再投递，短暂 DoesNotExist 有界重试。"""

from unittest.mock import MagicMock

import pytest
from celery.exceptions import MaxRetriesExceededError, Retry
from django.db import transaction

from apps.patch_mgmt import tasks as patch_tasks
from apps.patch_mgmt.constants import GovernanceTaskStatus, GovernanceTaskType
from apps.patch_mgmt.models import GovernanceTask
from apps.patch_mgmt.services import governance_service


def _make_pending_task() -> GovernanceTask:
    return GovernanceTask.objects.create(
        name="commit-visibility",
        task_type=GovernanceTaskType.ASSESS,
        execution_mode="now",
        status=GovernanceTaskStatus.PENDING,
        target_list=[],
        patch_list=[],
    )


@pytest.mark.django_db
def test_trigger_async_dispatches_only_after_commit(monkeypatch, django_capture_on_commit_callbacks):
    delayed: list[int] = []
    monkeypatch.setattr(
        patch_tasks.execute_governance_task,
        "delay",
        lambda task_id: delayed.append(task_id),
    )
    task = _make_pending_task()

    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            governance_service._trigger_async(task.id)
            assert delayed == []
        assert delayed == []

    assert delayed == [task.id]


@pytest.mark.django_db
def test_execute_governance_task_retries_does_not_exist_until_visible(monkeypatch):
    task = _make_pending_task()
    lookup_attempts = {"count": 0}
    original_get = GovernanceTask.objects.get

    def fake_get(*args, **kwargs):
        lookup_attempts["count"] += 1
        if lookup_attempts["count"] == 1:
            raise GovernanceTask.DoesNotExist
        return original_get(*args, **kwargs)

    monkeypatch.setattr(GovernanceTask.objects, "get", fake_get)
    monkeypatch.setattr(
        "apps.patch_mgmt.services.governance_convergence.reconcile_stale_history",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "apps.patch_mgmt.services.patch_execution_service._finalize_task_status",
        lambda _task: None,
    )

    def fake_retry(*args, **kwargs):
        assert kwargs.get("countdown") == 1
        patch_tasks.execute_governance_task(task.id)
        raise Retry("governance-task-lookup")

    monkeypatch.setattr(patch_tasks.execute_governance_task, "retry", fake_retry)

    with pytest.raises(Retry, match="governance-task-lookup"):
        patch_tasks.execute_governance_task(task.id)

    task.refresh_from_db()
    assert lookup_attempts["count"] == 2
    assert task.status == GovernanceTaskStatus.RUNNING
    assert task.started_at is not None


@pytest.mark.django_db
def test_execute_governance_task_stops_after_bounded_lookup_retries(monkeypatch, caplog):
    monkeypatch.setattr(
        patch_tasks.execute_governance_task,
        "retry",
        lambda *args, **kwargs: (_ for _ in ()).throw(MaxRetriesExceededError()),
    )

    missing_id = 9_999_999
    patch_tasks.execute_governance_task(missing_id)

    assert not GovernanceTask.objects.filter(pk=missing_id).exists()
    assert any("任务不存在" in record.getMessage() for record in caplog.records)


@pytest.mark.django_db
def test_execute_governance_task_does_not_retry_other_exceptions(monkeypatch):
    task = _make_pending_task()
    retry = MagicMock()
    monkeypatch.setattr(patch_tasks.execute_governance_task, "retry", retry)
    monkeypatch.setattr(
        "apps.patch_mgmt.services.governance_convergence.reconcile_stale_history",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("unexpected-db")),
    )

    with pytest.raises(RuntimeError, match="unexpected-db"):
        patch_tasks.execute_governance_task(task.id)

    retry.assert_not_called()
    task.refresh_from_db()
    assert task.status == GovernanceTaskStatus.PENDING

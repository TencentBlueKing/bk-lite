from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.services.collect_hit_state_service import CollectHitStateService


def _create_collect_task():
    return CollectModels.objects.create(
        name="multi-credential-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )


@pytest.mark.django_db
def test_collect_hit_state_service_marks_credential_failure_with_progressive_cooldown():
    task = _create_collect_task()
    first_now = timezone.make_aware(datetime(2026, 6, 3, 10, 0, 0))

    CollectHitStateService.mark_failure(
        task.id,
        "host:10.0.0.1",
        "cred-1",
        {"host": "10.0.0.1"},
        "credential",
        "auth failed",
        first_now,
    )

    state = CollectTaskCredentialHit.objects.get(task=task, object_key="host:10.0.0.1", credential_id="cred-1")
    assert state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert state.consecutive_failures == 1
    assert state.cooldown_level == 1
    assert state.next_retry_at == first_now + timedelta(hours=1)

    second_now = first_now + timedelta(hours=1, minutes=5)
    CollectHitStateService.mark_failure(
        task.id,
        "host:10.0.0.1",
        "cred-1",
        {"host": "10.0.0.1"},
        "credential",
        "auth failed again",
        second_now,
    )

    state.refresh_from_db()
    assert state.consecutive_failures == 2
    assert state.cooldown_level == 2
    assert state.next_retry_at == second_now + timedelta(hours=4)


@pytest.mark.django_db
def test_collect_hit_state_service_mark_success_clears_same_object_other_success():
    task = _create_collect_task()
    now = timezone.make_aware(datetime(2026, 6, 3, 11, 0, 0))
    CollectTaskCredentialHit.objects.create(
        task=task,
        object_key="host:10.0.0.2",
        credential_id="cred-1",
        status=CollectTaskCredentialHit.STATUS_SUCCESS,
    )
    CollectTaskCredentialHit.objects.create(
        task=task,
        object_key="host:10.0.0.2",
        credential_id="cred-2",
        status=CollectTaskCredentialHit.STATUS_UNTESTED,
    )

    CollectHitStateService.mark_success(task.id, "host:10.0.0.2", "cred-2", {"host": "10.0.0.2"}, now)

    first_state = CollectTaskCredentialHit.objects.get(task=task, object_key="host:10.0.0.2", credential_id="cred-1")
    second_state = CollectTaskCredentialHit.objects.get(task=task, object_key="host:10.0.0.2", credential_id="cred-2")
    assert first_state.status == CollectTaskCredentialHit.STATUS_UNTESTED
    assert second_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert second_state.last_success_at == now


@pytest.mark.django_db
def test_collect_hit_state_service_clear_by_credential_ids_removes_matching_states():
    task = _create_collect_task()
    CollectTaskCredentialHit.objects.create(task=task, object_key="host:1", credential_id="cred-1")
    CollectTaskCredentialHit.objects.create(task=task, object_key="host:1", credential_id="cred-2")
    CollectTaskCredentialHit.objects.create(task=task, object_key="host:2", credential_id="cred-2")

    deleted_count = CollectHitStateService.clear_by_credential_ids(task.id, ["cred-2"])

    assert deleted_count == 2
    assert CollectTaskCredentialHit.objects.filter(task=task).count() == 1
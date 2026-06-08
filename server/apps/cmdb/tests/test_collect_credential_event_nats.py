from datetime import datetime

import pytest
from django.utils import timezone
from unittest.mock import patch

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.nats.nats import receive_collect_credential_result
from apps.cmdb.tasks.celery_tasks import sync_collect_credential_results_task


@pytest.mark.django_db
def test_receive_collect_credential_result_marks_success_and_failure():
    task = CollectModels.objects.create(
        name="credential-event-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    failed_response = receive_collect_credential_result(
        data={
            "collect_task_id": task.id,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "success": False,
            "failure_kind": "credential",
            "error_message": "auth failed",
            "finished_at": timezone.make_aware(datetime(2026, 6, 3, 12, 0, 0)).isoformat(),
            "snapshot": {"host": "10.0.0.1"},
        }
    )

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert failed_response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert state.last_error == "auth failed"

    success_response = receive_collect_credential_result(
        data={
            "collect_task_id": task.id,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "success": True,
            "failure_kind": "",
            "error_message": "",
            "finished_at": timezone.make_aware(datetime(2026, 6, 3, 13, 0, 0)).isoformat(),
            "snapshot": {"host": "10.0.0.1"},
        }
    )

    state.refresh_from_db()
    assert success_response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert state.last_error == ""


@pytest.mark.django_db
def test_receive_collect_credential_result_processes_pushed_event_batch():
    task = CollectModels.objects.create(
        name="credential-push-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data={
            "events": [
                {
                    "collect_task_id": task.id,
                    "host": "10.0.0.1",
                    "credential_id": "cred-1",
                    "success": False,
                    "failure_kind": "credential",
                    "error_message": "auth failed",
                    "finished_at": timezone.make_aware(datetime(2026, 6, 3, 12, 0, 0)).isoformat(),
                    "snapshot": {"host": "10.0.0.1"},
                },
                {
                    "collect_task_id": task.id,
                    "host": "10.0.0.2",
                    "credential_id": "cred-1",
                    "success": True,
                    "failure_kind": "",
                    "error_message": "",
                    "finished_at": timezone.make_aware(datetime(2026, 6, 3, 12, 5, 0)).isoformat(),
                    "snapshot": {"host": "10.0.0.2"},
                },
            ],
            "next_since": timezone.make_aware(datetime(2026, 6, 3, 12, 5, 0)).isoformat(),
        }
    )

    failed_state = CollectTaskCredentialHit.objects.get(task=task, object_key="host:10.0.0.1", credential_id="cred-1")
    success_state = CollectTaskCredentialHit.objects.get(task=task, object_key="host:10.0.0.2", credential_id="cred-1")
    assert response["result"] is True
    assert response["processed"] == 2
    assert response["failed"] == 0
    assert failed_state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert success_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert response["next_since"] == timezone.make_aware(datetime(2026, 6, 3, 12, 5, 0)).isoformat()


@pytest.mark.django_db
def test_receive_collect_credential_result_logs_batch_summary(caplog):
    caplog.set_level("INFO", logger="cmdb")

    task = CollectModels.objects.create(
        name="credential-push-log-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    next_since = timezone.make_aware(datetime(2026, 6, 3, 12, 5, 0)).isoformat()

    receive_collect_credential_result(
        data={
            "events": [
                {
                    "collect_task_id": task.id,
                    "host": "10.0.0.1",
                    "credential_id": "cred-1",
                    "success": True,
                    "finished_at": timezone.make_aware(datetime(2026, 6, 3, 12, 0, 0)).isoformat(),
                    "snapshot": {"host": "10.0.0.1"},
                },
                {
                    "collect_task_id": task.id,
                    "host": "10.0.0.2",
                    "credential_id": "cred-1",
                    "success": False,
                    "failure_kind": "credential",
                    "error_message": "auth failed",
                    "finished_at": timezone.make_aware(datetime(2026, 6, 3, 12, 5, 0)).isoformat(),
                    "snapshot": {"host": "10.0.0.2"},
                },
            ],
            "next_since": next_since,
        }
    )

    assert "Received pushed collect credential result batch, count=2 next_since=" + next_since in caplog.text
    assert "Processed pushed collect credential result batch, processed=2 failed=0 next_since=" + next_since in caplog.text


def test_sync_collect_credential_results_task_is_disabled_in_push_mode(monkeypatch):
    result = sync_collect_credential_results_task()

    assert result == {
        "result": True,
        "skipped": True,
        "message": "collect credential results are received via NATS push",
    }
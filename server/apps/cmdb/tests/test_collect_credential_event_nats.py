import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from django.utils import timezone

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.nats.nats import receive_collect_credential_result
from apps.cmdb.tasks.celery_tasks import sync_collect_credential_results_task


pytestmark = [pytest.mark.integration, pytest.mark.django_db]


_STARGAZER_EVENT_SCRIPT = r"""
import asyncio
import json
import sys
from types import SimpleNamespace

from core.collection.contracts import build_collection_result_id
from core.collection.result_publisher import NatsResultPublisher

params = json.loads(sys.argv[1])
request = SimpleNamespace(
    task_id=params["run_id"],
    plugin_ref=params["plugin_ref"],
    params={"collect_task_id": params["collect_task_id"]},
)
lease = SimpleNamespace(
    fence=params["fence"],
    attempt_id=params["attempt_id"],
    owner_id="stargazer-pod-1",
)
result_id = build_collection_result_id(
    task_id=request.task_id,
    plugin_ref=request.plugin_ref,
    target=params["host"],
    fence=lease.fence,
    attempt_id=lease.attempt_id,
)
events = []

async def record_event(event):
    event["finished_at"] = params["finished_at"]
    events.append(event)

result = SimpleNamespace(
    target=params["host"],
    status=params["status"],
    attempts=params["attempts"],
    credential_id=params["credential_id"],
    error_code=params["error_code"],
    credential_failures=tuple(
        SimpleNamespace(**failure) for failure in params.get("credential_failures", [])
    ),
)
publisher = NatsResultPublisher(result_event_sink=record_event)
if "event_index" in params:
    event = publisher._build_credential_event(
        request=request,
        lease=lease,
        result_id=result_id,
        target=params["host"],
        credential_id=params["credential_id"],
        status=params["status"],
        error_code=params["error_code"],
        attempts=params["attempts"],
        event_index=params["event_index"],
    )
    event["finished_at"] = params["finished_at"]
    events.append(event)
else:
    asyncio.run(publisher._record_event(request, result, lease, result_id))
print(json.dumps(events))
"""


def _stargazer_events(**overrides):
    params = {
        "collect_task_id": overrides.pop("collect_task_id"),
        "run_id": "request-fingerprint",
        "plugin_ref": "snmp.config",
        "host": "10.0.0.1",
        "fence": 1,
        "attempt_id": "run-attempt-1",
        "status": "success",
        "error_code": "",
        "credential_id": "cred-1",
        "attempts": 1,
        "finished_at": "2026-08-14T00:00:00+00:00",
        "credential_failures": [],
        **overrides,
    }
    stargazer_dir = Path(__file__).resolve().parents[4] / "agents/stargazer"
    completed = subprocess.run(
        [
            str(stargazer_dir / ".venv/bin/python"),
            "-c",
            _STARGAZER_EVENT_SCRIPT,
            json.dumps(params),
        ],
        cwd=stargazer_dir,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def _v2_event(
    task_id,
    *,
    status="success",
    error_code="",
    credential_id="cred-1",
    event_index=0,
    finished_at="2026-08-14T00:00:00+00:00",
    attempt_id="run-attempt-1",
    host="10.0.0.1",
):
    events = _stargazer_events(
        collect_task_id=task_id,
        status=status,
        error_code=error_code,
        credential_id=credential_id,
        attempts=event_index + 1,
        attempt_id=attempt_id,
        host=host,
        finished_at=finished_at,
        event_index=event_index,
    )
    return events[0]


def _create_task(name):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[
            {"credential_id": "cred-1", "username": "admin", "password": "plain"},
            {"credential_id": "cred-2", "username": "backup", "password": "plain"},
        ],
    )


@pytest.mark.django_db
def test_receive_collect_credential_result_accepts_current_stargazer_success_event(caplog):
    caplog.set_level("INFO", logger="cmdb")
    task = CollectModels.objects.create(
        name="credential-v2-success-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data={
            "collect_task_id": task.id,
            "plugin_ref": "mysql.config",
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "status": "success",
            "error_code": "",
            "attempts": 1,
            "fence": 7,
            "result_id": "result-success",
        }
    )

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert state.last_error == ""
    assert "status=success" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error_code",
    [
        "auth_failed",
        "authentication_failed",
        "capability_denied",
        "snmp_error_status",
        "snmp_authorization_failed",
        "unauthorized",
    ],
)
def test_receive_collect_credential_result_maps_current_auth_error_to_credential_failure(error_code):
    task = CollectModels.objects.create(
        name=f"credential-v2-{error_code}-failure-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data=_v2_event(task.id, status="failed", error_code=error_code)
    )

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert state.last_error == error_code


@pytest.mark.django_db
def test_receive_collect_credential_result_deduplicates_redelivered_event():
    task = CollectModels.objects.create(
        name="credential-v2-redelivery-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )
    event = _v2_event(
        task.id, status="failed", error_code="authentication_failed"
    )

    first_response = receive_collect_credential_result(data=event)
    second_response = receive_collect_credential_result(data=event)

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert first_response["result"] is True
    assert second_response["result"] is True
    assert state.consecutive_failures == 1
    assert state.cooldown_level == 1


@pytest.mark.django_db
def test_actual_stargazer_rotation_events_reach_cmdb_once():
    task = _create_task("credential-real-producer-rotation-task")
    events = _stargazer_events(
        collect_task_id=task.id,
        status="success",
        attempts=2,
        credential_id="cred-2",
        attempt_id="snmp-rotation-attempt",
        credential_failures=[
            {
                "credential_id": "cred-1",
                "error_code": "snmp_authorization_failed",
            }
        ],
    )
    first = receive_collect_credential_result(data={"events": events})
    redelivered = receive_collect_credential_result(data={"events": events})

    failed = CollectTaskCredentialHit.objects.get(
        task=task, credential_id="cred-1"
    )
    succeeded = CollectTaskCredentialHit.objects.get(
        task=task, credential_id="cred-2"
    )
    assert first == {
        "result": True,
        "processed": 2,
        "failed": 0,
        "next_since": "",
        "errors": [],
    }
    assert redelivered["result"] is True
    assert failed.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert failed.consecutive_failures == 1
    assert failed.cooldown_level == 1
    assert succeeded.status == CollectTaskCredentialHit.STATUS_SUCCESS


@pytest.mark.django_db
def test_v2_event_rejects_scope_and_run_identity_tampering():
    task = _create_task("credential-v2-identity-task")
    scope_event = _v2_event(task.id)
    scope_event["scope_id"] = "another-task"
    fence_event = _v2_event(task.id, event_index=1)
    fence_event["fence"] = 2

    assert receive_collect_credential_result(data=scope_event) == {
        "result": False,
        "message": "scope_id conflicts with collect_task_id",
    }
    assert receive_collect_credential_result(data=fence_event) == {
        "result": False,
        "message": "result_id conflicts with run identity",
    }
    assert not CollectTaskCredentialHit.objects.filter(task=task).exists()


@pytest.mark.django_db
def test_v2_event_ignores_older_result_and_redelivery_without_extra_cooldown():
    task = _create_task("credential-v2-out-of-order-task")
    latest = _v2_event(
        task.id,
        status="failed",
        error_code="snmp_authorization_failed",
        finished_at="2026-08-14T01:00:00+00:00",
        attempt_id="latest-attempt",
    )
    older = _v2_event(
        task.id,
        status="success",
        finished_at="2026-08-14T00:00:00+00:00",
        attempt_id="older-attempt",
    )

    assert receive_collect_credential_result(data=latest)["result"] is True
    assert receive_collect_credential_result(data=older)["result"] is True
    assert receive_collect_credential_result(data=latest)["result"] is True

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert state.status == CollectTaskCredentialHit.STATUS_KNOWN_FAILED
    assert state.consecutive_failures == 1
    assert state.cooldown_level == 1
    assert state.last_result_id == latest["result_id"]


def test_v2_older_success_cannot_replace_newer_cross_credential_affinity():
    task = _create_task("credential-v2-cross-credential-order-task")
    latest = _v2_event(
        task.id,
        credential_id="cred-2",
        finished_at="2026-08-14T01:00:00+00:00",
        attempt_id="latest-attempt",
    )
    older = _v2_event(
        task.id,
        credential_id="cred-1",
        finished_at="2026-08-14T00:00:00+00:00",
        attempt_id="older-attempt",
    )

    assert receive_collect_credential_result(data=latest)["result"] is True
    assert receive_collect_credential_result(data=older)["result"] is True

    latest_state = CollectTaskCredentialHit.objects.get(
        task=task, credential_id="cred-2"
    )
    assert latest_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


def test_legacy_older_success_cannot_replace_newer_v2_affinity():
    task = _create_task("credential-mixed-version-order-task")
    latest = _v2_event(
        task.id,
        credential_id="cred-2",
        finished_at="2026-08-14T01:00:00+00:00",
        attempt_id="latest-attempt",
    )
    legacy_older = {
        "collect_task_id": task.id,
        "host": "10.0.0.1",
        "credential_id": "cred-1",
        "success": True,
        "finished_at": "2026-08-14T00:00:00+00:00",
    }

    assert receive_collect_credential_result(data=latest)["result"] is True
    assert receive_collect_credential_result(data=legacy_older)["result"] is True

    latest_state = CollectTaskCredentialHit.objects.get(
        task=task, credential_id="cred-2"
    )
    assert latest_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


def test_delayed_event_uses_observed_time_instead_of_stream_cursor_time():
    task = _create_task("credential-observed-time-order-task")
    latest = _v2_event(
        task.id,
        credential_id="cred-2",
        finished_at="2026-08-14T01:00:00+00:00",
        attempt_id="latest-attempt",
    )
    latest["observed_at"] = "2026-08-14T01:00:00+00:00"
    delayed_older = _v2_event(
        task.id,
        credential_id="cred-1",
        finished_at="2026-08-14T02:00:00+00:00",
        attempt_id="delayed-attempt",
    )
    delayed_older["observed_at"] = "2026-08-14T00:00:00+00:00"

    assert receive_collect_credential_result(data=latest)["result"] is True
    assert receive_collect_credential_result(data=delayed_older)["result"] is True

    latest_state = CollectTaskCredentialHit.objects.get(
        task=task, credential_id="cred-2"
    )
    assert latest_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-an-object", "event must be an object"),
        (
            {
                "collect_task_id": "not-an-integer",
                "host": "10.0.0.1",
                "credential_id": "cred-1",
                "status": "success",
            },
            "collect_task_id does not exist",
        ),
        (
            {
                "collect_task_id": 1,
                "host": "10.0.0.1",
                "credential_id": "cred-1",
                "status": "success",
                "snapshot": ["not", "an", "object"],
            },
            "snapshot must be an object",
        ),
        (
            {
                "collect_task_id": 1,
                "host": "10.0.0.1",
                "credential_id": "cred-1",
                "status": "success",
                "finished_at": "invalid-time",
            },
            "event time is invalid",
        ),
    ],
)
def test_collect_credential_result_rejects_malformed_event(payload, message):
    assert receive_collect_credential_result(data=payload) == {
        "result": False,
        "message": message,
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("error_code", "failure_kind"),
    [
        ("authentication_failed", "task"),
        ("plugin_timeout", "credential"),
    ],
)
def test_receive_collect_credential_result_rejects_conflicting_failure_kind(
    error_code, failure_kind
):
    task = CollectModels.objects.create(
        name=f"credential-conflicting-{error_code}-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    event = _v2_event(task.id, status="failed", error_code=error_code)
    event["failure_kind"] = failure_kind
    response = receive_collect_credential_result(data=event)

    assert response == {
        "result": False,
        "message": "error_code conflicts with failure_kind",
    }
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["success", "deferred", "unreachable"])
def test_receive_collect_credential_result_rejects_auth_error_for_non_failed_status(
    status,
):
    task = CollectModels.objects.create(
        name=f"credential-conflicting-{status}-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data=_v2_event(
            task.id, status=status, error_code="authentication_failed"
        )
    )

    assert response == {"result": False, "message": "status conflicts with error_code"}
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


@pytest.mark.django_db
def test_receive_collect_credential_result_keeps_deferred_event_retryable():
    task = CollectModels.objects.create(
        name="credential-v2-deferred-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data=_v2_event(task.id, status="deferred", error_code="rate_limited")
    )

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_UNTESTED
    assert state.next_retry_at is None
    assert state.last_error == "rate_limited"


@pytest.mark.django_db
def test_receive_collect_credential_result_rejects_conflicting_event_fields():
    task = CollectModels.objects.create(
        name="credential-conflicting-event-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    event = _v2_event(task.id)
    event["success"] = False
    response = receive_collect_credential_result(data=event)

    assert response == {"result": False, "message": "status conflicts with success"}
    assert not CollectTaskCredentialHit.objects.filter(task=task, credential_id="cred-1").exists()


@pytest.mark.django_db
def test_receive_collect_credential_result_rejects_unknown_event_version():
    task = CollectModels.objects.create(
        name="credential-unknown-event-version-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data={
            "event_version": 3,
            "collect_task_id": task.id,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "status": "success",
        }
    )

    assert response == {"result": False, "message": "unsupported event_version: 3"}
    assert not CollectTaskCredentialHit.objects.filter(task=task, credential_id="cred-1").exists()


@pytest.mark.django_db
def test_receive_collect_credential_result_requires_status_for_v2_event():
    task = CollectModels.objects.create(
        name="credential-v2-missing-status-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data={
            "event_version": 2,
            "collect_task_id": task.id,
            "host": "10.0.0.1",
            "credential_id": "cred-1",
            "success": True,
        }
    )

    assert response == {
        "result": False,
        "message": "status is required for event_version: 2",
    }
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, credential_id="cred-1"
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        ("failed", "plugin_timeout"),
        ("unreachable", "target_unreachable"),
    ],
)
def test_receive_collect_credential_result_keeps_task_failures_retryable(
    status, error_code
):
    task = CollectModels.objects.create(
        name=f"credential-v2-{status}-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    response = receive_collect_credential_result(
        data=_v2_event(task.id, status=status, error_code=error_code)
    )

    state = CollectTaskCredentialHit.objects.get(task=task, credential_id="cred-1")
    assert response["result"] is True
    assert state.status == CollectTaskCredentialHit.STATUS_UNTESTED
    assert state.last_error == error_code


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
def test_receive_collect_credential_result_keeps_valid_events_in_mixed_batch():
    task = CollectModels.objects.create(
        name="credential-mixed-push-task",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="host",
        cycle_value_type="cycle",
        credential=[{"credential_id": "cred-1", "username": "admin", "password": "plain"}],
    )

    valid_event = _v2_event(task.id)
    invalid_event = _v2_event(
        task.id,
        status="failed",
        error_code="authentication_failed",
        event_index=1,
    )
    invalid_event["host"] = "10.0.0.2"
    invalid_event["success"] = True
    response = receive_collect_credential_result(
        data={
            "events": [valid_event, invalid_event],
            "next_since": "cursor-2",
        }
    )

    success_state = CollectTaskCredentialHit.objects.get(
        task=task,
        object_key="host:10.0.0.1",
        credential_id="cred-1",
    )
    assert response["result"] is False
    assert response["processed"] == 1
    assert response["failed"] == 1
    assert response["next_since"] == "cursor-2"
    assert success_state.status == CollectTaskCredentialHit.STATUS_SUCCESS
    assert not CollectTaskCredentialHit.objects.filter(
        task=task, object_key="host:10.0.0.2"
    ).exists()


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

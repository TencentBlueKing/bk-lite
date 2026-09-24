from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import TriggerInvocation, Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow_orchestration.services.schedules import bind_schedule_timezones
from apps.workflow_orchestration.services.triggers import invoke_trigger, run_due_cron_triggers
from apps.workflow_orchestration.views import WorkflowTriggerViewSet


@pytest.fixture
def trigger_admin(db):
    return get_user_model().objects.create(username="trigger-admin", domain="example.com", is_superuser=True)


def _request(method, path, user, data=None, *, team=7):
    request = getattr(APIRequestFactory(), method)(
        path,
        data or {},
        format="json",
        HTTP_COOKIE=f"current_team={team}",
    )
    force_authenticate(request, user=user)
    return request


def _workflow():
    definition = {
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "passthrough",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "recipients": ["ops@example.com"],
                    "title": "Webhook 通知",
                    "body": "${workflow.input.message}",
                },
            }
        ]
    }
    workflow = Workflow.objects.create(
        name="Webhook 流程",
        team=[7],
        definition=definition,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
        canvas_metadata={
            "input_schema": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            }
        },
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=definition,
        canvas_metadata=workflow.canvas_metadata,
    )
    return workflow


@pytest.mark.django_db
def test_trigger_is_managed_by_workflow_draft_and_duplicate_invocation_is_idempotent(trigger_admin, mocker):
    workflow = _workflow()
    create = WorkflowTriggerViewSet.as_view({"post": "create"})
    created = create(
        _request(
            "post",
            "/triggers/",
            trigger_admin,
            {
                "workflow": workflow.id,
                "name": "发布回调",
                "trigger_type": "WEBHOOK",
                "enabled": True,
                "idempotency_window_seconds": 3600,
            },
        )
    )
    assert created.status_code == 405
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="发布回调",
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        team=[7],
        idempotency_window_seconds=3600,
    )
    conductor = mocker.patch("apps.workflow_orchestration.services.triggers.ConductorClient").return_value
    conductor.start_workflow.return_value = "triggered-conductor-1"
    invoke = WorkflowTriggerViewSet.as_view({"post": "invoke"})

    first = invoke(
        _request(
            "post",
            f"/triggers/{trigger.id}/invoke/",
            trigger_admin,
            {"idempotency_key": "event-42", "inputs": {"message": "deploy"}},
        ),
        pk=trigger.id,
    )
    duplicate = invoke(
        _request(
            "post",
            f"/triggers/{trigger.id}/invoke/",
            trigger_admin,
            {"idempotency_key": "event-42", "inputs": {"message": "deploy"}},
        ),
        pk=trigger.id,
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.data["id"] == first.data["id"]
    assert conductor.start_workflow.call_count == 1


@pytest.mark.django_db
def test_different_triggers_of_same_workflow_create_independent_execution_records(trigger_admin, mocker):
    workflow = _workflow()
    form_trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        node_key="trigger_form",
        name="人工表单",
        trigger_type=WorkflowTrigger.Type.FORM,
        enabled=True,
        team=[7],
    )
    webhook_trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        node_key="trigger_webhook",
        name="告警 Webhook",
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        team=[7],
    )
    conductor = mocker.patch("apps.workflow_orchestration.services.triggers.ConductorClient").return_value
    conductor.start_workflow.side_effect = ["conductor-form", "conductor-webhook"]
    invoke = WorkflowTriggerViewSet.as_view({"post": "invoke"})

    form_response = invoke(
        _request(
            "post",
            f"/triggers/{form_trigger.id}/invoke/",
            trigger_admin,
            {"inputs": {"message": "manual"}},
        ),
        pk=form_trigger.id,
    )
    webhook_response = invoke(
        _request(
            "post",
            f"/triggers/{webhook_trigger.id}/invoke/",
            trigger_admin,
            {"idempotency_key": "alert-42", "inputs": {"message": "alert"}},
        ),
        pk=webhook_trigger.id,
    )

    assert form_response.status_code == 201
    assert webhook_response.status_code == 201
    assert form_response.data["id"] != webhook_response.data["id"]
    assert {(item.trigger_type, item.trigger_id, item.input["message"]) for item in WorkflowExecution.objects.filter(workflow=workflow)} == {
        (WorkflowTrigger.Type.FORM, str(form_trigger.id), "manual"),
        (WorkflowTrigger.Type.WEBHOOK, str(webhook_trigger.id), "alert"),
    }
    assert conductor.start_workflow.call_count == 2


@pytest.mark.django_db
def test_trigger_cannot_be_created_outside_workflow_editor(trigger_admin):
    workflow = _workflow()
    create = WorkflowTriggerViewSet.as_view({"post": "create"})

    response = create(
        _request(
            "post",
            "/triggers/",
            trigger_admin,
            {
                "workflow": workflow.id,
                "name": "无效计划",
                "trigger_type": "CRON",
                "enabled": True,
                "config": {"expression": "not-a-cron", "timezone": "Asia/Shanghai"},
            },
        )
    )

    assert response.status_code == 405


@pytest.mark.django_db
def test_schedule_preview_uses_authenticated_user_timezone_without_registering_trigger(trigger_admin):
    trigger_admin.timezone = "Asia/Shanghai"
    preview = WorkflowTriggerViewSet.as_view({"post": "schedule_preview"})
    before = WorkflowTrigger.objects.count()

    response = preview(
        _request(
            "post",
            "/triggers/schedule-preview/",
            trigger_admin,
            {
                "config": {
                    "frequency": "daily",
                    "time": ["09:00", "18:30"],
                    "timezone": "UTC",
                },
                "count": 3,
            },
        )
    )

    assert response.status_code == 200
    assert response.data["timezone"] == "Asia/Shanghai"
    assert response.data["expressions"] == ["0 9 * * *", "30 18 * * *"]
    assert len(response.data["next_runs"]) == 3
    assert response.data["test_output"]["test"] is True
    assert response.data["test_output"]["timezone"] == "Asia/Shanghai"
    assert response.data["test_output"]["schedule"] == ["0 9 * * *", "30 18 * * *"]
    assert WorkflowTrigger.objects.count() == before


@pytest.mark.django_db
def test_schedule_preview_rejects_invalid_structured_config(trigger_admin):
    preview = WorkflowTriggerViewSet.as_view({"post": "schedule_preview"})

    response = preview(
        _request(
            "post",
            "/triggers/schedule-preview/",
            trigger_admin,
            {"config": {"frequency": "weekly", "time": ["09:00"], "weekdays": []}},
        )
    )

    assert response.status_code == 400
    assert "weekdays" in response.data["detail"]


@pytest.mark.django_db
def test_nats_test_session_uses_saved_draft_and_returns_captured_payload(trigger_admin, mocker):
    workflow = _workflow()
    workflow.canvas_metadata = {
        "trigger_nodes": [
            {
                "id": "trigger_nats",
                "name": "事件触发器（NATS）",
                "trigger_type": "NATS",
                "input_schema": {},
                "config": {},
            }
        ]
    }
    workflow.save(update_fields=("canvas_metadata", "updated_at"))
    create_session = WorkflowTriggerViewSet.as_view({"post": "nats_test_session"})
    listen = WorkflowTriggerViewSet.as_view({"post": "nats_test_listen"})

    created = create_session(
        _request(
            "post",
            "/triggers/nats-test-session/",
            trigger_admin,
            {"workflow_id": workflow.id, "node_key": "trigger_nats"},
        )
    )

    assert created.status_code == 200
    assert created.data["subject"].startswith(f"bklite.workflow.test.{workflow.id}.trigger_nats.")
    wait = mocker.patch(
        "apps.workflow_orchestration.views.wait_for_nats_test_event",
        return_value={
            "event": {
                "event_id": "evt-1",
                "occurred_at": "2026-09-18T10:00:00Z",
                "producer": "job-platform",
                "payload": {"status": "SUCCESS"},
            },
            "inputs": {"status": "SUCCESS"},
        },
    )

    captured = listen(
        _request(
            "post",
            "/triggers/nats-test-listen/",
            trigger_admin,
            {"token": created.data["token"]},
        )
    )

    assert captured.status_code == 200
    assert captured.data["inputs"] == {"status": "SUCCESS"}
    wait.assert_called_once_with(created.data["subject"])


@pytest.mark.django_db
def test_webhook_test_session_uses_saved_draft_and_returns_captured_body(trigger_admin, mocker):
    workflow = _workflow()
    workflow.canvas_metadata = {
        "trigger_nodes": [
            {
                "id": "trigger_webhook",
                "name": "Webhook 触发器",
                "trigger_type": "WEBHOOK",
                "input_schema": {},
                "config": {"response_mode": "IMMEDIATE"},
            }
        ]
    }
    workflow.save(update_fields=("canvas_metadata", "updated_at"))
    create_session = WorkflowTriggerViewSet.as_view({"post": "webhook_test_session"})
    listen = WorkflowTriggerViewSet.as_view({"post": "webhook_test_listen"})

    created = create_session(
        _request(
            "post",
            "/triggers/webhook-test-session/",
            trigger_admin,
            {"workflow_id": workflow.id, "node_key": "trigger_webhook"},
        )
    )

    assert created.status_code == 200
    assert created.data["timeout_seconds"] == 60
    wait = mocker.patch(
        "apps.workflow_orchestration.views.wait_for_webhook_test_event",
        return_value={"body": {"host": "10.0.0.8", "severity": "critical"}},
    )

    captured = listen(
        _request(
            "post",
            "/triggers/webhook-test-listen/",
            trigger_admin,
            {"token": created.data["token"]},
        )
    )

    assert captured.status_code == 200
    assert captured.data == {"body": {"host": "10.0.0.8", "severity": "critical"}}
    wait.assert_called_once_with(created.data["token"])


def test_published_schedule_captures_server_resolved_timezone_without_mutating_draft():
    draft = {
        "trigger_nodes": [
            {
                "id": "trigger_schedule",
                "trigger_type": "SCHEDULE",
                "config": {"frequency": "weekly", "time": ["09:05"], "weekdays": [1, 5], "timezone": "UTC"},
            }
        ]
    }

    published = bind_schedule_timezones(draft, timezone_name="Asia/Shanghai")

    assert published["trigger_nodes"][0]["config"] == {
        "frequency": "weekly",
        "time": ["09:05"],
        "weekdays": [1, 5],
        "expressions": ["5 9 * * 1,5"],
        "expression": "5 9 * * 1,5",
        "timezone": "Asia/Shanghai",
    }
    assert draft["trigger_nodes"][0]["config"]["timezone"] == "UTC"


@pytest.mark.django_db
def test_form_trigger_detail_is_tenant_scoped_for_generated_form(trigger_admin):
    workflow = _workflow()
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        node_key="trigger_form",
        name="巡检表单",
        trigger_type=WorkflowTrigger.Type.FORM,
        enabled=True,
        team=[7],
        input_schema={"type": "object", "properties": {"hostname": {"type": "string"}}},
    )
    retrieve = WorkflowTriggerViewSet.as_view({"get": "retrieve"})

    visible = retrieve(_request("get", f"/triggers/{trigger.id}/", trigger_admin), pk=trigger.id)
    other_team_request = _request("get", f"/triggers/{trigger.id}/", trigger_admin, team=8)
    hidden = retrieve(other_team_request, pk=trigger.id)

    assert visible.status_code == 200
    assert visible.data["node_key"] == "trigger_form"
    assert visible.data["input_schema"]["properties"]["hostname"]["type"] == "string"
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_expired_idempotency_key_can_start_a_new_execution(trigger_admin, mocker):
    workflow = _workflow()
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="Webhook",
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        team=[7],
        idempotency_window_seconds=60,
    )
    conductor = mocker.Mock()
    conductor.start_workflow.side_effect = ["execution-1", "execution-2"]
    first, created = invoke_trigger(
        trigger,
        inputs={"message": "one"},
        idempotency_key="reusable-key",
        started_by="trigger-admin",
        domain="example.com",
        client=conductor,
    )
    assert created is True
    TriggerInvocation.objects.filter(trigger=trigger).update(expires_at=timezone.now() - timedelta(seconds=1))

    second, created_again = invoke_trigger(
        trigger,
        inputs={"message": "two"},
        idempotency_key="reusable-key",
        started_by="trigger-admin",
        domain="example.com",
        client=conductor,
    )

    assert created_again is True
    assert second.id != first.id
    assert conductor.start_workflow.call_count == 2


@pytest.mark.django_db(transaction=True)
def test_invoke_trigger_starts_conductor_outside_open_transaction(trigger_admin, mocker):
    from django.db import connection

    workflow = _workflow()
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="Webhook",
        trigger_type=WorkflowTrigger.Type.WEBHOOK,
        enabled=True,
        team=[7],
        idempotency_window_seconds=60,
    )
    conductor = mocker.Mock()

    def assert_outside_transaction(*_args, **_kwargs):
        assert connection.in_atomic_block is False
        return "execution-outside"

    conductor.start_workflow.side_effect = assert_outside_transaction

    execution, created = invoke_trigger(
        trigger,
        inputs={"message": "one"},
        idempotency_key="outside-tx",
        started_by="trigger-admin",
        domain="example.com",
        client=conductor,
    )

    assert created is True
    assert execution.conductor_workflow_id == "execution-outside"
    assert TriggerInvocation.objects.get(trigger=trigger, idempotency_key="outside-tx").execution_id == execution.id


@pytest.mark.django_db
def test_due_cron_trigger_runs_once_and_moves_next_run_forward(mocker):
    workflow = _workflow()
    now = timezone.now()
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="每分钟",
        trigger_type=WorkflowTrigger.Type.SCHEDULE,
        enabled=True,
        team=[7],
        default_inputs={"message": "scheduled"},
        config={"expression": "* * * * *", "timezone": "Asia/Shanghai"},
        next_run_at=now - timedelta(seconds=1),
    )
    conductor = mocker.patch("apps.workflow_orchestration.services.triggers.ConductorClient").return_value
    conductor.start_workflow.return_value = "cron-execution-1"

    first = run_due_cron_triggers(now=now)
    second = run_due_cron_triggers(now=now)

    trigger.refresh_from_db()
    assert first == {"succeeded": 1, "skipped": 0, "failed": 0}
    assert second == {"succeeded": 0, "skipped": 0, "failed": 0}
    assert trigger.next_run_at > now
    assert conductor.start_workflow.call_count == 1


@pytest.mark.django_db
def test_due_cron_trigger_starts_independent_execution_when_same_workflow_is_still_active(mocker):
    workflow = _workflow()
    now = timezone.now()
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="每分钟",
        trigger_type=WorkflowTrigger.Type.SCHEDULE,
        enabled=True,
        team=[7],
        default_inputs={"message": "scheduled"},
        config={"expression": "* * * * *", "timezone": "Asia/Shanghai"},
        next_run_at=now - timedelta(seconds=1),
    )
    WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        started_by="workflow-scheduler",
    )
    conductor = mocker.patch("apps.workflow_orchestration.services.triggers.ConductorClient").return_value
    conductor.start_workflow.return_value = "cron-execution-while-active"

    summary = run_due_cron_triggers(now=now)

    trigger.refresh_from_db()
    assert summary == {"succeeded": 1, "skipped": 0, "failed": 0}
    assert trigger.next_run_at > now
    conductor.start_workflow.assert_called_once()
    executions = WorkflowExecution.objects.filter(workflow=workflow).order_by("created_at")
    assert executions.count() == 2
    assert executions.last().trigger_type == WorkflowTrigger.Type.SCHEDULE
    assert executions.last().trigger_id == str(trigger.id)

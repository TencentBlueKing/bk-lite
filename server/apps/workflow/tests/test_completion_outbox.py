from unittest.mock import MagicMock, patch

import pytest

from apps.workflow.models import Workflow, WorkflowCompletionOutbox, WorkflowExecution
from apps.workflow.services.completion_outbox import deliver_outbox_record, enqueue_async_callback
from apps.workflow.services.executions import apply_remote_execution


@pytest.mark.django_db
def test_terminal_sync_enqueues_async_callback_without_http():
    workflow = Workflow.objects.create(name="回调流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-cb",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        async_callback_context={
            "callback_url": "https://example.com/cb",
            "callback_token": "tok-wf-1",
            "operator": "system",
            "user": "alice",
            "domain": "example.com",
            "team_id": 7,
        },
        async_callback_key="wf-key-1",
    )

    with patch("apps.core.openapi.async_callback.requests.post") as post:
        apply_remote_execution(
            execution,
            {"status": "COMPLETED", "output": {"ok": True}, "tasks": [], "endTime": 1_700_000_000_000},
        )

    execution.refresh_from_db()
    record = WorkflowCompletionOutbox.objects.get(execution_id=execution.id)
    assert execution.status == WorkflowExecution.Status.SUCCEEDED
    assert record.status == WorkflowCompletionOutbox.Status.PENDING
    post.assert_not_called()


@pytest.mark.django_db
def test_async_callback_http_failure_does_not_change_execution_status():
    workflow = Workflow.objects.create(name="回调失败隔离", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.SUCCEEDED,
        team=[7],
        async_callback_context={
            "callback_url": "https://example.com/cb",
            "callback_token": "tok-wf-2",
            "operator": "system",
            "user": "alice",
            "domain": "example.com",
            "team_id": 7,
        },
        async_callback_key="wf-key-2",
    )
    record = enqueue_async_callback(execution)
    failed = MagicMock(status_code=500, json=MagicMock(return_value={"result": False}))

    with patch("apps.core.openapi.async_callback.SSRFValidator.validate_callback"), patch(
        "apps.core.openapi.async_callback.requests.post",
        return_value=failed,
    ):
        assert deliver_outbox_record(record.pk) is False

    execution.refresh_from_db()
    record.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.SUCCEEDED
    assert record.status != WorkflowCompletionOutbox.Status.DELIVERED


@pytest.mark.django_db
def test_async_callback_enqueue_failure_does_not_block_terminal_status():
    workflow = Workflow.objects.create(name="写入失败隔离", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-enqueue-fail",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        async_callback_context={
            "callback_url": "https://example.com/cb",
            "callback_token": "tok-wf-3",
            "operator": "system",
        },
        async_callback_key="wf-key-3",
    )

    with patch(
        "apps.workflow.services.completion_outbox.enqueue_async_callback",
        side_effect=RuntimeError("outbox write failed"),
    ):
        apply_remote_execution(
            execution,
            {"status": "COMPLETED", "output": {}, "tasks": [], "endTime": 1_700_000_000_000},
        )

    execution.refresh_from_db()
    assert execution.status == WorkflowExecution.Status.SUCCEEDED
    assert not WorkflowCompletionOutbox.objects.filter(execution_id=execution.id).exists()

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.services.interactions import expire_due_interactions
from apps.workflow_orchestration.views import WorkflowExecutionViewSet, WorkflowInteractionViewSet


@pytest.fixture
def approver(db):
    return get_user_model().objects.create(username="alice", domain="example.com", is_superuser=True)


def _request(method, path, user, data=None):
    request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def _pending_approval():
    workflow = Workflow.objects.create(name="发布审批", team=[7], definition={"tasks": []})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id=f"conductor-approval-{uuid.uuid4()}",
        status=WorkflowExecution.Status.WAITING_APPROVAL,
        team=[7],
        started_by="starter",
    )
    return WorkflowInteraction.objects.create(
        execution=execution,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve_release",
        conductor_task_id="human-task-1",
        title="确认发布",
        description="确认后继续下发",
        candidate_users=["alice", "bob"],
        public_context={"change_summary": "2 台主机"},
        team=[7],
    )


@pytest.mark.django_db(transaction=True)
def test_candidate_approval_is_created_by_real_submission_and_only_advances_once(approver, mocker):
    interaction = _pending_approval()
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    decide = WorkflowInteractionViewSet.as_view({"post": "decide"})

    approved = decide(
        _request("post", f"/interactions/{interaction.id}/decide/", approver, {"decision": "APPROVED", "comment": "已核对"}),
        pk=interaction.id,
    )
    repeated = decide(
        _request("post", f"/interactions/{interaction.id}/decide/", approver, {"decision": "REJECTED", "comment": "重复操作"}),
        pk=interaction.id,
    )

    assert approved.status_code == 200
    assert approved.data["status"] == "APPROVED"
    assert approved.data["operator"] == "alice"
    assert approved.data["output"]["approved"] is True
    assert approved.data["output"]["comment"] == "已核对"
    assert repeated.status_code == 409
    conductor.complete_task.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_candidate_with_view_only_workflow_scope_can_decide_approval(mocker):
    candidate = get_user_model().objects.create(username="alice", domain="example.com")
    candidate.group_list = [{"id": 7, "name": "Current"}]
    candidate.group_tree = []
    candidate.permission = {
        "workflow-orchestration": {
            "workflow-View",
            "workflow-Approve",
        }
    }
    interaction = _pending_approval()
    mocker.patch(
        "apps.workflow_orchestration.permissions.get_permission_rules",
        return_value={
            "team": [],
            "instance": [{"id": interaction.execution.workflow_id, "permission": ["View"]}],
        },
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    decide = WorkflowInteractionViewSet.as_view({"post": "decide"})

    response = decide(
        _request("post", f"/interactions/{interaction.id}/decide/", candidate, {"decision": "APPROVED"}),
        pk=interaction.id,
    )

    assert response.status_code == 200
    assert response.data["operator"] == "alice"
    conductor.complete_task.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_non_candidate_with_view_only_workflow_scope_cannot_decide_approval(mocker):
    non_candidate = get_user_model().objects.create(username="mallory", domain="example.com")
    non_candidate.group_list = [{"id": 7, "name": "Current"}]
    non_candidate.group_tree = []
    non_candidate.permission = {
        "workflow-orchestration": {
            "workflow-View",
            "workflow-Approve",
        }
    }
    interaction = _pending_approval()
    mocker.patch(
        "apps.workflow_orchestration.permissions.get_permission_rules",
        return_value={
            "team": [],
            "instance": [{"id": interaction.execution.workflow_id, "permission": ["View"]}],
        },
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    decide = WorkflowInteractionViewSet.as_view({"post": "decide"})

    response = decide(
        _request("post", f"/interactions/{interaction.id}/decide/", non_candidate, {"decision": "APPROVED"}),
        pk=interaction.id,
    )

    assert response.status_code == 403
    conductor.complete_task.assert_not_called()


@pytest.mark.django_db
def test_execution_detail_discovers_human_task_as_pending_approval(approver, mocker):
    workflow = Workflow.objects.create(name="发布审批", team=[7], definition={"tasks": []})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-human-discovery",
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        started_by="starter",
    )
    mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value.get_execution.return_value = {
        "status": "RUNNING",
        "tasks": [
            {
                "taskId": "human-task-discovery",
                "referenceTaskName": "approve_release",
                "taskType": "HUMAN",
                "status": "IN_PROGRESS",
                "inputData": {
                    "interactionType": "APPROVAL",
                    "title": "确认发布",
                    "description": "核对变更摘要",
                    "candidates": ["alice", "bob"],
                    "publicContext": {"change_summary": "2 台主机"},
                },
            }
        ],
    }
    detail = WorkflowExecutionViewSet.as_view({"get": "retrieve"})

    response = detail(_request("get", f"/executions/{execution.id}/", approver), pk=execution.id)

    assert response.status_code == 200
    assert response.data["status"] == "WAITING_APPROVAL"
    interaction = WorkflowInteraction.objects.get(execution=execution)
    assert interaction.status == WorkflowInteraction.Status.PENDING
    assert interaction.candidate_users == ["alice", "bob"]
    assert interaction.public_context == {"change_summary": "2 台主机"}


@pytest.mark.django_db
def test_due_approval_times_out_without_impersonating_a_rejection(approver, mocker):
    interaction = _pending_approval()
    interaction.due_at = timezone.now() - timedelta(seconds=1)
    interaction.save(update_fields=("due_at", "updated_at"))
    conductor = mocker.Mock()

    summary = expire_due_interactions(client=conductor)

    interaction.refresh_from_db()
    assert summary == {"timed_out": 1, "failed": 0}
    assert interaction.status == WorkflowInteraction.Status.TIMED_OUT
    assert interaction.output == {
        "approved": None,
        "operator": None,
        "comment": None,
        "handled_at": None,
        "timed_out_at": interaction.handled_at.isoformat(),
    }
    conductor.complete_task.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_approval_persists_delivery_intent_before_calling_conductor(approver, mocker):
    from django.db import connection

    interaction = _pending_approval()
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value

    def assert_outside_transaction(**_kwargs):
        assert connection.in_atomic_block is False
        claimed = WorkflowInteraction.objects.get(pk=interaction.id)
        assert claimed.status == WorkflowInteraction.Status.PENDING
        assert claimed.delivery_token is not None
        assert claimed.delivery_payload["status"] == WorkflowInteraction.Status.APPROVED

    conductor.complete_task.side_effect = assert_outside_transaction
    decide = WorkflowInteractionViewSet.as_view({"post": "decide"})

    response = decide(
        _request("post", f"/interactions/{interaction.id}/decide/", approver, {"decision": "APPROVED"}),
        pk=interaction.id,
    )

    assert response.status_code == 200
    interaction.refresh_from_db()
    assert interaction.status == WorkflowInteraction.Status.APPROVED
    assert interaction.delivery_token is None
    assert interaction.delivery_payload == {}


@pytest.mark.django_db
def test_delivery_retry_abandons_after_max_attempts(mocker):
    from apps.workflow_orchestration.services.conductor import ConductorUnavailable
    from apps.workflow_orchestration.services.interactions import MAX_DELIVERY_ATTEMPTS, retry_pending_interaction_deliveries

    interaction = _pending_approval()
    interaction.delivery_token = uuid.uuid4()
    interaction.delivery_started_at = timezone.now() - timedelta(minutes=5)
    interaction.delivery_payload = {
        "status": WorkflowInteraction.Status.APPROVED,
        "operator": "alice",
        "operator_domain": "example.com",
        "decision": "APPROVED",
        "comment": "",
        "output": {"approved": True},
        "handled_at": timezone.now().isoformat(),
        "worker_id": "bklite-human-alice",
        "_delivery_attempts": MAX_DELIVERY_ATTEMPTS - 1,
    }
    interaction.save(update_fields=("delivery_token", "delivery_started_at", "delivery_payload", "updated_at"))
    conductor = mocker.Mock()
    conductor.complete_task.side_effect = ConductorUnavailable("down")

    summary = retry_pending_interaction_deliveries(client=conductor, retry_after_seconds=1)

    interaction.refresh_from_db()
    assert summary["failed"] == 1
    assert summary["abandoned"] == 1
    assert interaction.delivery_token is None
    assert interaction.status == WorkflowInteraction.Status.PENDING


@pytest.mark.django_db
def test_delivery_retry_abandons_immediately_on_conductor_conflict(mocker):
    from apps.workflow_orchestration.services.conductor import ConductorConflict
    from apps.workflow_orchestration.services.interactions import retry_pending_interaction_deliveries

    interaction = _pending_approval()
    interaction.delivery_token = uuid.uuid4()
    interaction.delivery_started_at = timezone.now() - timedelta(minutes=5)
    interaction.delivery_payload = {
        "status": WorkflowInteraction.Status.APPROVED,
        "operator": "alice",
        "operator_domain": "example.com",
        "decision": "APPROVED",
        "comment": "",
        "output": {"approved": True},
        "handled_at": timezone.now().isoformat(),
        "worker_id": "bklite-human-alice",
        "_delivery_attempts": 0,
    }
    interaction.save(update_fields=("delivery_token", "delivery_started_at", "delivery_payload", "updated_at"))
    conductor = mocker.Mock()
    conductor.complete_task.side_effect = ConductorConflict("conflict")

    summary = retry_pending_interaction_deliveries(client=conductor, retry_after_seconds=1)

    interaction.refresh_from_db()
    assert summary["abandoned"] == 1
    assert interaction.delivery_token is None

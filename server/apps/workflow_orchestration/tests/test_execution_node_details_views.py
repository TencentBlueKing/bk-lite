import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.views import WorkflowExecutionViewSet


@pytest.fixture
def viewer(db):
    return get_user_model().objects.create(username="alice", domain="example.com", is_superuser=True)


def _request(path, user, *, team="7", query=None):
    request = APIRequestFactory().get(path, query or {})
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _execution(*, team=7):
    workflow = Workflow.objects.create(name="生产变更前置检查", team=[team], definition={})
    definition = {
        "tasks": [
            {
                "name": "bklite_inspection_group_targets",
                "taskReferenceName": "group_targets",
                "type": "SIMPLE",
                "inputParameters": {"targets": "${workflow.input.targets}"},
            },
            {
                "name": "parallel_scan",
                "taskReferenceName": "parallel_scan",
                "type": "FORK_JOIN",
                "forkTasks": [
                    [{"name": "bklite_inspection_scan_linux", "taskReferenceName": "scan_linux", "type": "SIMPLE"}],
                    [{"name": "bklite_inspection_scan_windows", "taskReferenceName": "scan_windows", "type": "SIMPLE"}],
                ],
            },
            {"name": "parallel_scan_join", "taskReferenceName": "parallel_scan_join", "type": "JOIN", "joinOn": ["scan_linux", "scan_windows"]},
            {
                "name": "approval",
                "taskReferenceName": "approve_release",
                "type": "HUMAN",
                "inputParameters": {"title": "确认生产目标范围", "candidates": ["alice", "bob"]},
            },
            {"name": "bklite_inspection_report", "taskReferenceName": "report", "type": "SIMPLE"},
        ]
    }
    return WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=3,
        conductor_workflow_id=f"conductor-{uuid.uuid4()}",
        status=WorkflowExecution.Status.WAITING_APPROVAL,
        team=[team],
        started_by="starter",
        input={"targets": ["node:linux-1"], "credential": "******"},
        definition_snapshot=definition,
        tasks=[
            {
                "task_id": "task-group",
                "reference": "group_targets",
                "type": "bklite_inspection_group_targets",
                "system_type": "SIMPLE",
                "status": "COMPLETED",
                "worker_id": "worker-1",
                "started_at": "2026-09-02T01:00:00Z",
                "finished_at": "2026-09-02T01:00:01Z",
                "duration_ms": 1000,
                "retry_count": 0,
                "iteration": 0,
                "retried_task_id": "",
                "input": {"targets": ["node:linux-1"]},
                "output": {"linux": ["node:linux-1"]},
                "reason": "",
            },
            {
                "task_id": "task-windows-1",
                "reference": "scan_windows",
                "type": "bklite_inspection_scan_windows",
                "system_type": "SIMPLE",
                "status": "FAILED",
                "worker_id": "worker-2",
                "started_at": "2026-09-02T01:00:02Z",
                "finished_at": "2026-09-02T01:00:04Z",
                "duration_ms": 2000,
                "retry_count": 0,
                "iteration": 0,
                "retried_task_id": "",
                "input": {"credential": "******"},
                "output": {},
                "reason": "主机响应超时",
            },
            {
                "task_id": "task-windows-2",
                "reference": "scan_windows",
                "type": "bklite_inspection_scan_windows",
                "system_type": "SIMPLE",
                "status": "FAILED",
                "worker_id": "worker-2",
                "started_at": "2026-09-02T01:00:05Z",
                "finished_at": "2026-09-02T01:00:07Z",
                "duration_ms": 2000,
                "retry_count": 1,
                "iteration": 0,
                "retried_task_id": "task-windows-1",
                "input": {"credential": "******"},
                "output": {},
                "reason": "主机响应超时",
            },
        ],
    )


@pytest.mark.django_db
def test_node_summary_uses_frozen_definition_and_selects_earliest_actionable_approval(viewer):
    execution = _execution()
    interaction = WorkflowInteraction.objects.create(
        execution=execution,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve_release",
        conductor_task_id="human-task-1",
        title="确认生产目标范围",
        candidate_users=["alice", "bob"],
        public_context={"target_scope": "生产环境 · 12 台主机"},
        team=[7],
    )
    view = WorkflowExecutionViewSet.as_view({"get": "nodes"})

    response = view(_request(f"/executions/{execution.id}/nodes/", viewer), pk=execution.id)

    assert response.status_code == 200
    assert response.data["default_node_reference"] == "approve_release"
    assert [item["reference"] for item in response.data["nodes"]] == [
        "__start__",
        "group_targets",
        "parallel_scan",
        "scan_linux",
        "scan_windows",
        "parallel_scan_join",
        "approve_release",
        "report",
        "__end__",
    ]
    by_reference = {item["reference"]: item for item in response.data["nodes"]}
    assert by_reference["scan_linux"]["parent_reference"] == "parallel_scan"
    assert by_reference["scan_linux"]["branch_label"] == "分支 1"
    assert by_reference["scan_windows"]["state"] == "FAILED"
    assert by_reference["scan_windows"]["instance_count"] == 2
    assert by_reference["scan_windows"]["state_counts"] == {"FAILED": 2}
    assert by_reference["approve_release"]["state"] == "ACTIONABLE"
    assert by_reference["approve_release"]["actionable_interaction_ids"] == [str(interaction.id)]
    assert by_reference["report"]["state"] == "PENDING"


@pytest.mark.django_db
def test_node_detail_returns_only_selected_instance_and_declared_approval_context(viewer):
    execution = _execution()
    interaction = WorkflowInteraction.objects.create(
        execution=execution,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve_release",
        conductor_task_id="human-task-1",
        title="确认生产目标范围",
        description="核对目标和维护窗口",
        candidate_users=["alice", "bob"],
        public_context={"target_scope": "生产环境 · 12 台主机"},
        team=[7],
    )
    view = WorkflowExecutionViewSet.as_view({"get": "node_detail"})

    approval_response = view(
        _request(f"/executions/{execution.id}/nodes/approve_release/", viewer),
        pk=execution.id,
        node_reference="approve_release",
    )
    retry_response = view(
        _request(
            f"/executions/{execution.id}/nodes/scan_windows/",
            viewer,
            query={"instance_id": "task-windows-1"},
        ),
        pk=execution.id,
        node_reference="scan_windows",
    )

    assert approval_response.status_code == 200
    assert approval_response.data["interaction"] == {
        "id": str(interaction.id),
        "type": "APPROVAL",
        "status": "PENDING",
        "title": "确认生产目标范围",
        "description": "核对目标和维护窗口",
        "public_context": {"target_scope": "生产环境 · 12 台主机"},
        "candidate_users": ["alice", "bob"],
        "can_act": True,
        "operator": "",
        "decision": "",
        "comment": "",
        "created_at": interaction.created_at.isoformat(),
        "due_at": None,
        "handled_at": None,
    }
    assert "targets" not in approval_response.data["interaction"]["public_context"]
    assert retry_response.status_code == 200
    assert retry_response.data["selected_instance_id"] == "task-windows-1"
    assert [item["id"] for item in retry_response.data["instances"]] == ["task-windows-1", "task-windows-2"]
    assert retry_response.data["execution_info"]["status"] == "FAILED"
    assert retry_response.data["error"]["message"] == "主机响应超时"


@pytest.mark.django_db
def test_node_endpoints_are_team_scoped(viewer):
    execution = _execution(team=8)
    nodes = WorkflowExecutionViewSet.as_view({"get": "nodes"})
    detail = WorkflowExecutionViewSet.as_view({"get": "node_detail"})

    nodes_response = nodes(_request(f"/executions/{execution.id}/nodes/", viewer), pk=execution.id)
    detail_response = detail(
        _request(f"/executions/{execution.id}/nodes/__start__/", viewer),
        pk=execution.id,
        node_reference="__start__",
    )

    assert nodes_response.status_code == 404
    assert detail_response.status_code == 404

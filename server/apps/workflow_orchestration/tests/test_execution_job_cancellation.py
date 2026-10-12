import pytest

from apps.workflow_orchestration.models import AtomExecution, Workflow, WorkflowExecution
from apps.workflow_orchestration.services.execution_job_cancellation import cancel_linked_job_tasks, collect_linked_job_task_ids
from apps.workflow_orchestration.services.job_platform import JobPlatformExecutor


@pytest.mark.django_db
def test_collect_linked_job_task_ids_dedupes_field_and_output():
    workflow = Workflow.objects.create(name="取消联动", team=[7], definition={"tasks": []})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        definition_snapshot={"tasks": []},
        started_by="operator",
    )
    AtomExecution.objects.create(
        execution=execution,
        task_reference="a",
        atom_key="bklite_custom_script",
        job_task_id=101,
        output={"job_task_ids": [101, 102]},
    )
    AtomExecution.objects.create(
        execution=execution,
        task_reference="b",
        atom_key="bklite_custom_script",
        job_task_id=102,
        output={"job_task_ids": ["103", "bad"]},
    )

    assert collect_linked_job_task_ids(execution) == [101, 102, 103]


@pytest.mark.django_db
def test_cancel_linked_job_tasks_requests_cancel_and_keeps_going_on_failures():
    workflow = Workflow.objects.create(name="取消联动", team=[7], definition={"tasks": []})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        status=WorkflowExecution.Status.RUNNING,
        team=[7],
        definition_snapshot={"tasks": []},
        started_by="operator",
    )
    AtomExecution.objects.create(
        execution=execution,
        task_reference="a",
        atom_key="bklite_custom_script",
        job_task_id=101,
        output={"job_task_ids": [101, 102]},
    )

    class FakeClient:
        def __init__(self):
            self.calls = []

        def cancel_automation_execution(self, data, actor_context):
            self.calls.append((data, actor_context))
            if data["task_id"] == 102:
                return {"result": False, "message": "作业已终态"}
            return {"result": True, "data": {"task_id": data["task_id"], "status": "cancelling"}}

    client = FakeClient()
    results = cancel_linked_job_tasks(
        execution,
        actor={"username": "operator", "domain": "example.com"},
        executor=JobPlatformExecutor(client=client),
    )

    assert [item["task_id"] for item in results] == [101, 102]
    assert results[0] == {"task_id": 101, "ok": True, "status": "cancelling"}
    assert results[1]["ok"] is False
    assert results[1]["error_type"] == "JobPlatformError"
    assert client.calls[0][1]["authorized_team_ids"] == [7]

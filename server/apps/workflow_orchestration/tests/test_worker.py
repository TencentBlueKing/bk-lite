import threading
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.workflow_orchestration.management.commands.run_workflow_worker import Command
from apps.workflow_orchestration.models import AtomExecution, Workflow, WorkflowExecution
from apps.workflow_orchestration.services.conductor import ConductorUnavailable
from apps.workflow_orchestration.services.data_contracts import seal_sensitive_inputs


def test_worker_startup_registers_built_in_and_package_tasks_then_polls_each_once(mocker):
    client = mocker.patch("apps.workflow_orchestration.management.commands.run_workflow_worker.ConductorClient").return_value
    client.poll_task.return_value = None
    register_packages = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.register_atom_packages",
        return_value={"packages": 1, "created_atoms": 1, "updated_atoms": 0},
    )
    package_definition = {"name": "custom_package_task", "retryCount": 0, "timeoutSeconds": 30}
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.package_atom_task_definitions",
        return_value=[package_definition],
    )
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.ATOM_HANDLERS",
        {"built_in_task": mocker.Mock()},
    )

    Command().handle(once=True)

    register_packages.assert_called_once_with()
    registered = client.register_task_definitions.call_args.args[0]
    assert package_definition in registered
    assert [call.args[0] for call in client.poll_task.call_args_list] == ["built_in_task", "custom_package_task"]
    assert all(call.args[1].startswith("bklite-") for call in client.poll_task.call_args_list)


def test_worker_refuses_to_start_when_conductor_task_registration_is_unavailable(mocker):
    client = mocker.patch("apps.workflow_orchestration.management.commands.run_workflow_worker.ConductorClient").return_value
    client.register_task_definitions.side_effect = ConductorUnavailable("offline")
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.register_atom_packages",
        return_value={"packages": 0, "created_atoms": 0, "updated_atoms": 0},
    )
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.package_atom_task_definitions",
        return_value=[],
    )

    with pytest.raises(RuntimeError, match="Conductor 不可用"):
        Command().handle(once=True)

    client.poll_task.assert_not_called()


def test_worker_once_keeps_polling_built_in_tasks_when_optional_package_registry_is_degraded(mocker):
    client = mocker.patch("apps.workflow_orchestration.management.commands.run_workflow_worker.ConductorClient").return_value
    client.poll_task.side_effect = ConductorUnavailable("temporary outage")
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.register_atom_packages",
        side_effect=RuntimeError("broken optional package"),
    )
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.package_atom_task_definitions",
        return_value=[],
    )
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_worker.ATOM_HANDLERS",
        {"built_in_task": mocker.Mock()},
    )

    Command().handle(once=True)

    client.register_task_definitions.assert_called_once()
    client.poll_task.assert_called_once()


@pytest.mark.django_db
def test_worker_rejects_trusted_atom_task_after_its_local_execution_context_was_removed(mocker):
    client = mocker.Mock()

    Command._execute_task(
        client,
        "worker-1",
        "bklite_job_execute",
        {
            "taskId": "orphan-task",
            "workflowInstanceId": "removed-execution",
            "inputData": {"execution_id": "00000000-0000-0000-0000-000000000000"},
        },
        handler=mocker.Mock(return_value={"should_not": "run"}),
    )

    result = client.update_task.call_args.args[0]
    assert result["status"] == "FAILED"
    assert result["reasonForIncompletion"] == "ValueError: atom execution failed"


@pytest.mark.django_db
def test_redelivery_does_not_steal_an_active_atom_execution_lease(mocker):
    workflow = Workflow.objects.create(name="租约中流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="workflow-active-lease",
        team=[7],
    )
    AtomExecution.objects.create(
        execution=execution,
        task_reference="remote_change",
        attempt=1,
        status=AtomExecution.Status.RUNNING,
        lease_expires_at=timezone.now() + timedelta(minutes=1),
    )
    client = mocker.Mock()
    handler = mocker.Mock(return_value={"changed": True})

    Command._execute_task(
        client,
        "worker-2",
        "bklite_job_execute",
        {
            "taskId": "redelivered-task",
            "workflowInstanceId": "workflow-active-lease",
            "referenceTaskName": "remote_change",
            "retryCount": 0,
            "inputData": {"execution_id": str(execution.id)},
        },
        handler=handler,
        heartbeat_interval=0.1,
    )

    handler.assert_not_called()
    assert client.update_task.call_args.args[0]["status"] == "IN_PROGRESS"


@pytest.mark.django_db
def test_transient_conductor_heartbeat_failure_does_not_fail_the_atom(mocker):
    workflow = Workflow.objects.create(name="心跳容错流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="workflow-heartbeat",
        team=[7],
    )
    release = threading.Event()

    def slow_handler(_inputs):
        release.wait(timeout=1)
        return {"ok": True}

    client = mocker.Mock()
    heartbeat_calls = 0

    def update_task(_result):
        nonlocal heartbeat_calls
        heartbeat_calls += 1
        if heartbeat_calls == 1:
            raise ConductorUnavailable("temporary outage")

    client.update_task.side_effect = update_task
    timer = threading.Timer(0.05, release.set)
    timer.start()
    try:
        Command._execute_task(
            client,
            "worker-1",
            "bklite_notification",
            {
                "taskId": "heartbeat-task",
                "workflowInstanceId": "workflow-heartbeat",
                "referenceTaskName": "notify",
                "inputData": {"execution_id": str(execution.id)},
            },
            handler=slow_handler,
            heartbeat_interval=0.01,
        )
    finally:
        timer.cancel()

    assert client.update_task.call_args_list[-1].args[0]["status"] == "COMPLETED"
    assert AtomExecution.objects.get(execution=execution).status == AtomExecution.Status.COMPLETED


@pytest.mark.django_db
def test_worker_reports_success(mocker):
    client = mocker.Mock()
    handler = mocker.Mock(return_value={"ok": True})

    Command._execute_task(
        client,
        "worker-1",
        "bklite_inspection_group_targets",
        {"taskId": "task-1", "workflowInstanceId": "workflow-1", "inputData": {"targets": []}},
        handler=handler,
    )

    client.update_task.assert_called_once_with(
        {
            "workflowInstanceId": "workflow-1",
            "taskId": "task-1",
            "workerId": "worker-1",
            "status": "COMPLETED",
            "outputData": {"ok": True},
        }
    )


@pytest.mark.django_db
def test_worker_failure_does_not_leak_input(mocker):
    client = mocker.Mock()

    Command._execute_task(
        client,
        "worker-1",
        "bklite_inspection_group_targets",
        {"taskId": "task-1", "workflowInstanceId": "workflow-1", "inputData": {"token": "sensitive"}},
        handler=mocker.Mock(side_effect=RuntimeError("sensitive")),
    )

    result = client.update_task.call_args.args[0]
    assert result["status"] == "FAILED"
    assert "sensitive" not in result["reasonForIncompletion"]


@pytest.mark.django_db
def test_worker_only_decrypts_sensitive_envelope_for_handler_and_persists_mask(mocker):
    workflow = Workflow.objects.create(name="敏感输入流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="workflow-sensitive-1",
        team=[7],
    )
    metadata = {
        "data_contract": {
            "version": 1,
            "systemContextVersion": 1,
            "inputs": [{"key": "api_token", "sensitive": True}],
            "constants": [],
            "outputs": [],
        }
    }
    sealed = seal_sensitive_inputs({"execution_id": str(execution.id), "api_token": "secret-value"}, metadata)
    client = mocker.Mock()
    handler = mocker.Mock(return_value={"ok": True})

    Command._execute_task(
        client,
        "worker-1",
        "bklite_notification",
        {
            "taskId": "task-sensitive-1",
            "workflowInstanceId": "workflow-sensitive-1",
            "referenceTaskName": "echo",
            "inputData": sealed,
        },
        handler=handler,
    )

    payload = handler.call_args.args[0]
    assert payload["execution_id"] == str(execution.id)
    assert payload["api_token"] == "secret-value"
    assert payload["__bklite_context"]["organization_id"] == 7
    assert payload["__bklite_context"]["execution_id"] == str(execution.id)
    persisted = AtomExecution.objects.get(execution=execution).input
    assert persisted["api_token"] == "***"
    assert "__bklite_context" not in persisted


@pytest.mark.django_db
def test_worker_injects_trusted_execution_context_only_for_declared_atoms(mocker):
    workflow = Workflow.objects.create(name="OpsPilot 原子流程", team=[7], definition={})
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="workflow-opspilot-1",
        team=[7],
        started_by="alice",
        domain="example.com",
        trigger_type="FORM",
    )
    client = mocker.Mock()
    handler = mocker.Mock(return_value={"message": "done"})

    Command._execute_task(
        client,
        "worker-1",
        "bklite_agent",
        {
            "taskId": "task-opspilot-1",
            "workflowInstanceId": "workflow-opspilot-1",
            "referenceTaskName": "agent",
            "inputData": {"agent_id": 1, "message": "inspect"},
        },
        handler=handler,
    )

    payload = handler.call_args.args[0]
    assert payload["message"] == "inspect"
    assert payload["__bklite_context"] == {
        "execution_id": str(execution.id),
        "workflow_id": str(workflow.id),
        "workflow_version": 1,
        "organization_id": 7,
        "actor": {"username": "alice", "domain": "example.com"},
        "trigger_type": "FORM",
    }
    assert "__bklite_context" not in AtomExecution.objects.get(execution=execution).input


@pytest.mark.django_db
def test_worker_heartbeats_while_atom_is_running(mocker):
    client = mocker.Mock()
    release = threading.Event()
    started = threading.Event()

    def slow_handler(_inputs):
        started.set()
        release.wait(timeout=1)
        return {"ok": True}

    timer = threading.Timer(0.05, release.set)
    timer.start()
    try:
        Command._execute_task(
            client,
            "worker-1",
            "bklite_inspection_group_targets",
            {"taskId": "task-1", "workflowInstanceId": "workflow-1", "inputData": {"targets": []}},
            handler=slow_handler,
            heartbeat_interval=0.01,
        )
    finally:
        timer.cancel()

    assert started.is_set()
    statuses = [call.args[0]["status"] for call in client.update_task.call_args_list]
    assert "IN_PROGRESS" in statuses
    assert statuses[-1] == "COMPLETED"


def test_production_supervisor_starts_the_conductor_worker_command():
    project_root = Path(__file__).resolve().parents[4]
    config = (project_root / "server/support-files/release/supervisor/workflow_orchestration_worker.conf").read_text()

    assert "command=python manage.py run_workflow_worker" in config
    assert "celery -A apps.core.celery worker" not in config


@pytest.mark.django_db
def test_redelivered_conductor_task_reuses_terminal_result_without_repeating_atom(mocker):
    workflow = Workflow.objects.create(name="通用流程", team=[7], definition={})
    WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="workflow-1",
        team=[7],
    )
    client = mocker.Mock()
    handler = mocker.Mock(return_value={"changed": True})
    task = {
        "taskId": "task-1",
        "workflowInstanceId": "workflow-1",
        "referenceTaskName": "remote_change",
        "retryCount": 0,
        "inputData": {"action": "restart"},
    }

    Command._execute_task(client, "worker-1", "bklite_job_execute", task, handler=handler)
    Command._execute_task(client, "worker-2", "bklite_job_execute", task, handler=handler)

    handler.assert_called_once_with(
        {
            "action": "restart",
            "__bklite_context": {
                "execution_id": str(WorkflowExecution.objects.get(conductor_workflow_id="workflow-1").id),
                "workflow_id": str(workflow.id),
                "workflow_version": 1,
                "organization_id": 7,
                "actor": {"username": "", "domain": "domain.com"},
                "trigger_type": "FORM",
            },
        }
    )
    assert AtomExecution.objects.count() == 1
    assert [call.args[0]["status"] for call in client.update_task.call_args_list] == ["COMPLETED", "COMPLETED"]


@pytest.mark.django_db
def test_repeatable_engine_verifier_persists_cross_system_ids(mocker):
    class FakeConductor:
        def __init__(self):
            self.inputs = {}

        def register_workflow(self, _definition):
            return None

        def start_workflow(self, _name, *, version, inputs, correlation_id=""):
            self.inputs = inputs
            return "conductor-verifier-1"

        def get_execution(self, _workflow_id):
            return {
                "status": "COMPLETED",
                "output": {},
                "tasks": [
                    {
                        "taskId": "task-verifier-1",
                        "referenceTaskName": "condition",
                        "taskType": "SWITCH",
                        "status": "COMPLETED",
                        "inputData": {"left_0": self.inputs.get("value"), "right_0": "ok"},
                        "outputData": {},
                    }
                ],
            }

    fake = FakeConductor()
    mocker.patch(
        "apps.workflow_orchestration.management.commands.verify_workflow_orchestration_engine.ConductorClient",
        return_value=fake,
    )
    output = StringIO()

    call_command("verify_workflow_orchestration_engine", team=7, timeout=5, stdout=output)

    evidence = output.getvalue()
    assert '"conductor_workflow_id": "conductor-verifier-1"' in evidence
    assert '"engine_task": "SWITCH"' in evidence

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.workflow_orchestration.models import AtomDefinition, Workflow, WorkflowExecution, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import ensure_platform_atom
from apps.workflow_orchestration.services.atoms import ATOM_CATALOG
from apps.workflow_orchestration.services.definitions import build_health_inspection_definition
from apps.workflow_orchestration.views import WorkflowExecutionViewSet, WorkflowViewSet, _node_debug_input_schema


@pytest.fixture
def operator(db):
    return get_user_model().objects.create(username="workflow-operator", domain="example.com", is_superuser=True)


def _request(method, path, user, data=None):
    request = getattr(APIRequestFactory(), method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def _execution(*, status=WorkflowExecution.Status.RUNNING):
    definition = build_health_inspection_definition()
    workflow = Workflow.objects.create(
        name="可控制流程",
        team=[7],
        definition=definition,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=definition)
    return WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        conductor_workflow_id="conductor-control-1",
        status=status,
        team=[7],
        definition_snapshot=definition,
        started_by="workflow-operator",
    )


def _notification_task(reference: str, *, body: object = "测试通知") -> dict:
    ensure_platform_atom(
        ATOM_CATALOG["bklite_notification"],
        username="workflow-operator",
        domain="example.com",
    )
    return {
        "name": "bklite_notification",
        "taskReferenceName": reference,
        "type": "SIMPLE",
        "inputParameters": {
            "notification_type": "EMAIL",
            "channel_id": 1,
            "recipients": ["ops@example.com"],
            "title": "流程调试",
            "body": body,
        },
    }


def test_pause_and_resume_are_not_exposed_in_mvp():
    assert not hasattr(WorkflowExecutionViewSet, "pause")
    assert not hasattr(WorkflowExecutionViewSet, "resume")


def test_node_debug_validates_only_the_trigger_inputs_used_by_this_test():
    schema = {
        "type": "object",
        "properties": {
            "targets": {"type": "array", "items": {"type": "string"}},
            "report_template": {"type": "object"},
        },
        "required": ["targets", "report_template"],
        "additionalProperties": False,
    }

    assert _node_debug_input_schema(schema, {"targets": ["manual:11"]}, task_reference="scan") == {
        "type": "object",
        "properties": {"targets": {"type": "array", "items": {"type": "string"}}},
        "required": ["targets"],
        "additionalProperties": False,
    }
    assert _node_debug_input_schema(schema, {}, task_reference="") == schema


@pytest.mark.django_db
def test_operator_can_terminate_and_rerun_the_same_frozen_version(operator, mocker):
    execution = _execution()
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-rerun-2"
    terminate = WorkflowExecutionViewSet.as_view({"post": "terminate"})
    launch_plan = WorkflowExecutionViewSet.as_view({"get": "launch_plan"})
    rerun = WorkflowExecutionViewSet.as_view({"post": "rerun"})

    terminated = terminate(
        _request("post", f"/executions/{execution.id}/terminate/", operator, {"reason": "人工取消"}),
        pk=execution.id,
    )
    execution.status = WorkflowExecution.Status.TERMINATED
    execution.save(update_fields=("status", "updated_at"))
    plan = launch_plan(_request("get", f"/executions/{execution.id}/launch-plan/", operator), pk=execution.id)
    restarted = rerun(
        _request(
            "post",
            f"/executions/{execution.id}/rerun/",
            operator,
            {"launch_token": plan.data["launch_token"], "inputs": {}},
        ),
        pk=execution.id,
    )

    assert terminated.status_code == 200
    assert terminated.data["status"] == "TERMINATING"
    assert plan.status_code == 200
    assert restarted.status_code == 201
    assert restarted.data["workflow_version"] == 1
    assert restarted.data["parent_execution"] == str(execution.id)
    conductor.terminate_workflow.assert_called_once_with("conductor-control-1", reason="人工取消")
    conductor.start_workflow.assert_called_once()


@pytest.mark.django_db
def test_debug_runs_request_draft_without_saving_or_changing_published_version(operator, mocker):
    execution = _execution(status=WorkflowExecution.Status.SUCCEEDED)
    workflow = execution.workflow
    workflow.definition = {"tasks": [_notification_task("draft_notification")]}
    workflow.save(update_fields=("definition", "updated_at"))
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-debug-1"
    debug = WorkflowViewSet.as_view({"post": "debug"})

    request_definition = {"tasks": [_notification_task("page_notification")]}
    response = debug(
        _request("post", f"/workflows/{workflow.id}/debug/", operator, {"inputs": {"value": "draft"}, "definition": request_definition}),
        pk=workflow.id,
    )

    assert response.status_code == 201, response.data
    assert response.data["mode"] == "DEBUG"
    assert response.data["workflow_version"] == 0
    assert response.data["definition_snapshot"]["tasks"][0]["taskReferenceName"] == "page_notification"
    workflow.refresh_from_db()
    assert workflow.current_version == 1
    assert workflow.definition["tasks"][0]["taskReferenceName"] == "draft_notification"


@pytest.mark.django_db
def test_debug_uses_selected_trigger_schema_and_context(operator, mocker):
    workflow = Workflow.objects.create(
        name="Webhook 调试",
        team=[7],
        definition={"tasks": [_notification_task("notify_webhook")]},
    )
    metadata = {
        "trigger_nodes": [
            {
                "id": "trigger_form",
                "name": "人工表单",
                "trigger_type": "FORM",
                "input_schema": {
                    "type": "object",
                    "properties": {"operator": {"type": "string"}},
                    "required": ["operator"],
                    "additionalProperties": False,
                },
                "config": {},
            },
            {
                "id": "trigger_webhook",
                "name": "Webhook",
                "trigger_type": "WEBHOOK",
                "input_schema": {
                    "type": "object",
                    "properties": {"body": {"type": "object", "properties": {}, "additionalProperties": True}},
                    "required": ["body"],
                    "additionalProperties": False,
                },
                "config": {"response_mode": "IMMEDIATE"},
            },
        ],
        "return_nodes": [],
        "edges": [
            {"id": "start-form", "source": "trigger_form", "target": "notify_webhook"},
            {"id": "start-webhook", "source": "trigger_webhook", "target": "notify_webhook"},
        ],
    }
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-webhook-debug"
    debug = WorkflowViewSet.as_view({"post": "debug"})

    response = debug(
        _request(
            "post",
            f"/workflows/{workflow.id}/debug/",
            operator,
            {"inputs": {"body": {"count": 3}}, "trigger_id": "trigger_webhook", "canvas_metadata": metadata},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 201, response.data
    assert response.data["trigger_type"] == "WEBHOOK"
    assert response.data["trigger_id"] == "trigger_webhook"


@pytest.mark.django_db
def test_debug_registers_enabled_package_atom_by_stable_key(operator, mocker):
    atom = AtomDefinition.objects.create(
        key="custom.debug-summary",
        name="调试汇总",
        category="数据处理",
        driver="WORKER",
        built_in=False,
        source_type=AtomDefinition.SourceType.PACKAGE,
        team=[7],
        execution_config={"worker_task_type": "bklite_notification"},
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
        error_types=["INVALID_INPUT"],
        required_permissions=["workflow.atom.execute"],
        idempotent=True,
        idempotency_key="execution_id:task_id",
    )
    workflow = Workflow.objects.create(
        name="自定义原子调试",
        team=[7],
        definition={"tasks": [{"name": atom.key, "taskReferenceName": "summary", "type": "SIMPLE"}]},
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-custom-debug"
    debug = WorkflowViewSet.as_view({"post": "debug"})

    response = debug(_request("post", f"/workflows/{workflow.id}/debug/", operator, {"inputs": {}}), pk=workflow.id)

    assert response.status_code == 201
    task = response.data["definition_snapshot"]["tasks"][0]
    assert "__bklite_atom_version" not in task.get("inputParameters", {})
    assert response.data["resource_snapshot"]["atoms"] == [{"key": atom.key}]
    registered = conductor.register_task_definitions.call_args.args[0]
    assert any(item["name"] == atom.key for item in registered)


@pytest.mark.django_db
def test_debug_runs_one_simple_node_with_temporary_inputs(operator, mocker):
    execution = _execution(status=WorkflowExecution.Status.SUCCEEDED)
    workflow = execution.workflow
    incomplete_first = _notification_task("first", body="等待测试覆盖")
    incomplete_first["inputParameters"].pop("body")
    workflow.definition = {
        "tasks": [
            incomplete_first,
            _notification_task("second", body="第二个节点"),
        ]
    }
    workflow.save(update_fields=("definition", "updated_at"))
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-node-debug"
    debug = WorkflowViewSet.as_view({"post": "debug"})

    response = debug(
        _request(
            "post",
            f"/workflows/{workflow.id}/debug/",
            operator,
            {
                "inputs": {},
                "task_reference": "first",
                "confirmed": True,
                "node_inputs": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "recipients": ["ops@example.com"],
                    "title": "流程调试",
                    "body": "临时通知",
                },
            },
        ),
        pk=workflow.id,
    )

    assert response.status_code == 201, response.data
    assert response.data["debug_kind"] == "NODE"
    assert response.data["debug_task_reference"] == "first"
    assert response.data["definition_snapshot"]["tasks"] == [
        {
            "name": "bklite_notification",
            "taskReferenceName": "first",
            "type": "SIMPLE",
            "inputParameters": {
                "notification_type": "EMAIL",
                "channel_id": 1,
                "recipients": ["ops@example.com"],
                "title": "流程调试",
                "body": "临时通知",
            },
        }
    ]
    conductor.start_workflow.assert_called_once()


@pytest.mark.django_db
def test_debug_rejects_breakpoint_mode_in_mvp(operator, mocker):
    execution = _execution(status=WorkflowExecution.Status.SUCCEEDED)
    workflow = execution.workflow
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    debug = WorkflowViewSet.as_view({"post": "debug"})

    response = debug(
        _request(
            "post",
            f"/workflows/{workflow.id}/debug/",
            operator,
            {"inputs": {}, "breakpoint_before": "second"},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 400
    assert response.data["detail"] == "MVP 不支持断点调试"
    conductor.start_workflow.assert_not_called()


@pytest.mark.django_db
def test_validate_checks_request_draft_without_saving(operator):
    workflow = Workflow.objects.create(
        name="当前草稿",
        team=[7],
        definition={"tasks": [_notification_task("stored")]},
    )
    validate = WorkflowViewSet.as_view({"post": "validate"})
    response = validate(
        _request(
            "post",
            f"/workflows/{workflow.id}/validate/",
            operator,
            {"definition": {"tasks": [_notification_task("current_page")]}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 200
    workflow.refresh_from_db()
    assert workflow.definition["tasks"][0]["taskReferenceName"] == "stored"

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models.operation_log import OperationLog
from apps.workflow_orchestration.models import (
    AtomDefinition,
    ExecutionArtifact,
    Workflow,
    WorkflowExecution,
    WorkflowInteraction,
    WorkflowTrigger,
    WorkflowVersion,
)
from apps.workflow_orchestration.services.atom_registry import ensure_platform_atom
from apps.workflow_orchestration.services.atoms import ATOM_CATALOG
from apps.workflow_orchestration.services.definitions import (
    build_health_inspection_canvas_metadata,
    build_health_inspection_definition,
    compile_disabled_nodes,
)
from apps.workflow_orchestration.views import ExecutionArtifactViewSet, WorkflowExecutionViewSet, WorkflowInteractionViewSet, WorkflowViewSet


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create(username="workflow-admin", domain="example.com", is_superuser=True)


def _request(factory, method, path, user, data=None):
    request = getattr(factory, method)(path, data or {}, format="json")
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=user)
    return request


def _configured_health_definition():
    definition = build_health_inspection_definition()
    definition["tasks"][0]["inputParameters"].update(
        {
            "script_type": "shell",
            "script_content": 'printf \'{"cpu":{"usage_percent":42}}\'',
            "execution_params": "",
            "timeout_seconds": 600,
        }
    )
    definition["tasks"][1]["inputParameters"]["template_snapshot"] = {
        "object_key": "workflow-orchestration/templates/frozen/health.docx",
        "format": "docx",
        "sha256": "a" * 64,
        "size": 128,
        "filename_prefix": "health",
    }
    return definition


def _notification_task(reference: str, *, body: str = "流程通知") -> dict:
    return {
        "name": "bklite_notification",
        "taskReferenceName": reference,
        "type": "SIMPLE",
        "inputParameters": {
            "notification_type": "EMAIL",
            "channel_id": 1,
            "recipients": ["ops@example.com"],
            "title": "流程通知",
            "body": body,
        },
    }


def _enable_notification() -> AtomDefinition:
    return ensure_platform_atom(
        ATOM_CATALOG["bklite_notification"],
        username="workflow-admin",
        domain="example.com",
    )


@pytest.mark.django_db
def test_create_stores_native_conductor_definition(superuser):
    factory = APIRequestFactory()
    view = WorkflowViewSet.as_view({"post": "create"})

    response = view(_request(factory, "post", "/workflows/", superuser, {"name": "主机健康巡检"}))

    assert response.status_code == 201
    workflow = Workflow.objects.get()
    assert workflow.team == [7]
    assert workflow.definition["schemaVersion"] == 2
    assert "spec" not in workflow.definition


@pytest.mark.django_db
def test_create_rejects_duplicate_active_workflow_name_in_same_organization(superuser):
    Workflow.objects.create(name="重复流程", team=[7], definition={})
    create = WorkflowViewSet.as_view({"post": "create"})

    response = create(_request(APIRequestFactory(), "post", "/workflows/", superuser, {"name": "  重复流程  ", "starter": "blank"}))

    assert response.status_code == 400
    assert response.data["name"] == ["同一组织下已存在同名流程"]
    assert Workflow.objects.filter(team=[7]).count() == 1


@pytest.mark.django_db
def test_workflow_name_can_be_reused_by_another_organization_or_after_soft_delete(superuser):
    deleted = Workflow.objects.create(
        name="可复用流程",
        team=[7],
        definition={},
    )
    Workflow.all_objects.filter(pk=deleted.pk).update(deleted_at=timezone.now())
    create = WorkflowViewSet.as_view({"post": "create"})

    same_organization = create(_request(APIRequestFactory(), "post", "/workflows/", superuser, {"name": deleted.name, "starter": "blank"}))
    other_organization_request = _request(
        APIRequestFactory(),
        "post",
        "/workflows/",
        superuser,
        {"name": deleted.name, "starter": "blank"},
    )
    other_organization_request.COOKIES["current_team"] = "8"
    other_organization = create(other_organization_request)

    assert same_organization.status_code == 201
    assert other_organization.status_code == 201


@pytest.mark.django_db
def test_rename_and_duplicate_reject_another_active_workflow_name(superuser):
    source = Workflow.objects.create(name="源流程", team=[7], definition={})
    Workflow.objects.create(name="已存在流程", team=[7], definition={})
    rename = WorkflowViewSet.as_view({"patch": "partial_update"})
    duplicate = WorkflowViewSet.as_view({"post": "duplicate"})

    renamed = rename(
        _request(
            APIRequestFactory(),
            "patch",
            f"/workflows/{source.id}/",
            superuser,
            {"name": "已存在流程"},
        ),
        pk=source.id,
    )
    copied = duplicate(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{source.id}/duplicate/",
            superuser,
            {"name": "已存在流程"},
        ),
        pk=source.id,
    )

    assert renamed.status_code == 400
    assert renamed.data["name"] == ["同一组织下已存在同名流程"]
    assert copied.status_code == 400
    assert copied.data["name"] == ["同一组织下已存在同名流程"]


@pytest.mark.django_db
def test_database_rejects_concurrent_duplicate_active_workflow_name():
    Workflow.objects.create(name="数据库唯一流程", team=[7], definition={})

    with pytest.raises(IntegrityError), transaction.atomic():
        Workflow.objects.create(name="数据库唯一流程", team=[7], definition={})

    assert Workflow.objects.filter(name="数据库唯一流程", team=[7]).count() == 1


@pytest.mark.django_db
def test_duplicate_uses_validated_name_from_confirmation(superuser):
    source = Workflow.objects.create(
        name="源流程",
        description="保留说明",
        team=[7],
        definition={"name": "source", "schemaVersion": 2, "version": 1, "tasks": []},
        canvas_metadata={"positions": {}},
    )
    duplicate = WorkflowViewSet.as_view({"post": "duplicate"})

    response = duplicate(
        _request(APIRequestFactory(), "post", f"/workflows/{source.id}/duplicate/", superuser, {"name": "用户填写的副本"}),
        pk=source.id,
    )

    assert response.status_code == 201
    copied = Workflow.objects.get(pk=response.data["id"])
    assert copied.name == "用户填写的副本"
    assert copied.description == source.description
    assert copied.definition == source.definition
    assert copied.canvas_metadata == source.canvas_metadata


@pytest.mark.django_db
def test_duplicate_rejects_blank_name(superuser):
    source = Workflow.objects.create(
        name="源流程",
        team=[7],
        definition={"name": "source", "schemaVersion": 2, "version": 1, "tasks": []},
        canvas_metadata={"positions": {}},
    )
    duplicate = WorkflowViewSet.as_view({"post": "duplicate"})

    response = duplicate(
        _request(APIRequestFactory(), "post", f"/workflows/{source.id}/duplicate/", superuser, {"name": "   "}),
        pk=source.id,
    )

    assert response.status_code == 400
    assert Workflow.objects.count() == 1


@pytest.mark.django_db
def test_publish_excludes_disabled_simple_node_but_keeps_it_in_draft(superuser, mocker):
    _enable_notification()
    definition = {
        "name": "disabled-node-draft",
        "version": 1,
        "schemaVersion": 2,
        "tasks": [
            _notification_task("disabled_transform", body="停用"),
            _notification_task("active_transform", body="启用"),
        ],
    }
    workflow = Workflow.objects.create(
        name="停用节点流程",
        team=[7],
        definition=definition,
        canvas_metadata={"disabled_nodes": ["disabled_transform"]},
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    publish = WorkflowViewSet.as_view({"post": "publish"})

    response = publish(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{workflow.id}/publish/",
            superuser,
            {"definition": definition, "canvas_metadata": {"disabled_nodes": ["disabled_transform"]}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 200
    assert [task["taskReferenceName"] for task in WorkflowVersion.objects.get(workflow=workflow).definition["tasks"]] == ["active_transform"]
    workflow.refresh_from_db()
    assert [task["taskReferenceName"] for task in workflow.definition["tasks"]] == ["disabled_transform", "active_transform"]
    assert workflow.canvas_metadata["disabled_nodes"] == ["disabled_transform"]
    conductor.register_workflow.assert_called_once()


@pytest.mark.django_db
def test_validate_blocks_reference_to_disabled_node_output(superuser):
    definition = {
        "name": "broken-disabled-node",
        "version": 1,
        "schemaVersion": 2,
        "tasks": [
            _notification_task("disabled_transform", body="停用"),
            {
                "name": "bklite_notification",
                "taskReferenceName": "active_transform",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "body": "${disabled_transform.output.value}",
                },
            },
        ],
    }
    workflow = Workflow.objects.create(name="停用引用流程", team=[7], definition=definition)
    validate = WorkflowViewSet.as_view({"post": "validate"})

    response = validate(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{workflow.id}/validate/",
            superuser,
            {"definition": definition, "canvas_metadata": {"disabled_nodes": ["disabled_transform"]}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 400
    assert "停用节点 disabled_transform 的输出仍被引用" in response.data["errors"][0]


def test_disabled_node_reference_name_is_allowed_as_a_plain_input_literal():
    definition = {
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "disabled_transform",
                "type": "SIMPLE",
                "inputParameters": {"body": "停用"},
            },
            {
                "name": "bklite_notification",
                "taskReferenceName": "active_transform",
                "type": "SIMPLE",
                "inputParameters": {"body": "disabled_transform"},
            },
        ]
    }

    compiled = compile_disabled_nodes(definition, {"disabled_nodes": ["disabled_transform"]})

    assert compiled["tasks"][0]["inputParameters"]["body"] == "disabled_transform"


@pytest.mark.django_db
def test_workflow_list_is_server_paginated_and_filtered(superuser):
    production = Workflow.objects.create(name="生产巡检", team=[7], definition={}, current_version=1, enabled=True, has_draft=True)
    WorkflowTrigger.objects.create(
        workflow=production,
        name="定时",
        trigger_type=WorkflowTrigger.Type.SCHEDULE,
        enabled=True,
        team=[7],
    )
    WorkflowExecution.objects.create(
        workflow=production,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.SUCCEEDED,
    )
    Workflow.objects.create(name="测试巡检", team=[7], definition={})
    Workflow.objects.create(
        name="表单草稿",
        team=[7],
        definition={},
        canvas_metadata={"trigger_nodes": [{"id": "form", "trigger_type": "FORM"}]},
    )
    list_view = WorkflowViewSet.as_view({"get": "list"})

    response = list_view(_request(APIRequestFactory(), "get", "/workflows/?query=生产&page=1&page_size=1", superuser))

    assert response.data["count"] == 1
    assert response.data["items"][0]["name"] == "生产巡检"
    assert response.data["items"][0]["trigger_summary"] == ["SCHEDULE"]
    assert response.data["items"][0]["recent_execution_status"] == "SUCCEEDED"

    form_response = list_view(_request(APIRequestFactory(), "get", "/workflows/?trigger_type=FORM", superuser))
    assert form_response.data["count"] == 1
    assert form_response.data["items"][0]["name"] == "表单草稿"

    published = list_view(_request(APIRequestFactory(), "get", "/workflows/?status=PUBLISHED", superuser))
    assert published.data["count"] == 1
    assert published.data["items"][0]["name"] == "生产巡检"

    draft = list_view(_request(APIRequestFactory(), "get", "/workflows/?status=DRAFT", superuser))
    assert draft.data["count"] == 2
    assert "生产巡检" not in {item["name"] for item in draft.data["items"]}

    enabled = list_view(_request(APIRequestFactory(), "get", "/workflows/?enabled=true", superuser))
    assert enabled.data["count"] == 1
    assert enabled.data["items"][0]["name"] == "生产巡检"


@pytest.mark.django_db
def test_dashboard_returns_only_current_team_actionable_mvp_summary(superuser):
    workflow = Workflow.objects.create(
        name="生产流程",
        team=[7],
        definition={},
        status=Workflow.Status.PUBLISHED,
        current_version=1,
    )
    other_team_workflow = Workflow.objects.create(
        name="其他组织流程",
        team=[8],
        definition={},
        status=Workflow.Status.PUBLISHED,
        current_version=1,
    )
    Workflow.objects.create(name="草稿", team=[7], definition={})

    statuses = [
        WorkflowExecution.Status.SUCCEEDED,
        WorkflowExecution.Status.SUCCEEDED,
        WorkflowExecution.Status.FAILED,
        WorkflowExecution.Status.TIMED_OUT,
        WorkflowExecution.Status.RUNNING,
    ]
    executions = [
        WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=1,
            team=[7],
            status=execution_status,
            started_by="operator",
        )
        for execution_status in statuses
    ]
    executions[1].has_warnings = True
    executions[1].warning_count = 1
    executions[1].save(update_fields=("has_warnings", "warning_count", "updated_at"))
    debug_execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.FAILED,
        mode=WorkflowExecution.Mode.DEBUG,
    )
    other_team_execution = WorkflowExecution.objects.create(
        workflow=other_team_workflow,
        workflow_version=1,
        team=[8],
        status=WorkflowExecution.Status.FAILED,
    )
    old_execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.FAILED,
    )
    WorkflowExecution.objects.filter(pk=old_execution.pk).update(created_at=timezone.now() - timedelta(days=8))
    WorkflowInteraction.objects.create(
        execution=executions[-1],
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve",
        conductor_task_id="approval-dashboard",
        title="生产审批",
        candidate_users=[superuser.username],
        team=[7],
    )
    WorkflowInteraction.objects.create(
        execution=other_team_execution,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve",
        conductor_task_id="approval-other-team",
        title="其他组织审批",
        candidate_users=[superuser.username],
        team=[8],
    )
    WorkflowInteraction.objects.create(
        execution=executions[-1],
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approve-other-user",
        conductor_task_id="approval-other-user",
        title="其他人的审批",
        candidate_users=["another-user"],
        team=[7],
    )

    view = WorkflowExecutionViewSet.as_view({"get": "dashboard"})
    response = view(_request(APIRequestFactory(), "get", "/executions/dashboard/", superuser))

    assert response.status_code == 200
    assert response.data["kpis"] == {
        "workflow_total": 2,
        "published_workflows": 1,
        "enabled_workflows": 0,
        "draft_workflows": 2,
        "today_executions": 5,
        "success_rate": 50.0,
        "running_executions": 1,
        "queued_executions": 0,
        "failed_executions": 2,
        "pending_approvals": 1,
    }
    assert len(response.data["trend"]) == 7
    assert sum(item["total"] for item in response.data["trend"]) == 5
    status_counts = {item["status"]: item["count"] for item in response.data["status_distribution"]}
    assert status_counts[WorkflowExecution.Status.SUCCEEDED] == 2
    assert status_counts[WorkflowExecution.Status.FAILED] == 1
    assert status_counts[WorkflowExecution.Status.TIMED_OUT] == 1
    assert status_counts[WorkflowExecution.Status.RUNNING] == 1
    recent_ids = {item["id"] for item in response.data["recent_executions"]}
    assert str(debug_execution.id) not in recent_ids
    assert str(other_team_execution.id) not in recent_ids
    assert str(old_execution.id) in recent_ids
    assert len(response.data["pending_approvals"]) == 1
    assert response.data["pending_approvals"][0]["title"] == "生产审批"
    assert response.data["pending_approvals"][0]["workflow_name"] == "生产流程"


@pytest.mark.django_db
def test_publish_and_run_freeze_version_and_authorize_targets(superuser, mocker):
    workflow = Workflow.objects.create(
        name="主机健康巡检",
        team=[7],
        definition=_configured_health_definition(),
        canvas_metadata=build_health_inspection_canvas_metadata(),
        created_by=superuser.username,
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-1"
    nodes = mocker.patch("apps.workflow_orchestration.views.NodeMgmt").return_value
    nodes.get_authorized_execution_targets_by_ids.return_value = [
        {"id": "linux-1", "name": "linux", "ip": "10.0.0.1", "operating_system": "linux"},
        {"id": "windows-1", "name": "windows", "ip": "10.0.0.2", "operating_system": "windows"},
    ]
    factory = APIRequestFactory()
    publish = WorkflowViewSet.as_view({"post": "publish"})
    publish_response = publish(
        _request(
            factory,
            "post",
            f"/workflows/{workflow.id}/publish/",
            superuser,
            {
                "name": "生产主机健康巡检",
                "description": "发布当前页面中的草稿",
                "definition": workflow.definition,
                "canvas_metadata": workflow.canvas_metadata,
            },
        ),
        pk=workflow.id,
    )
    assert publish_response.status_code == 200, publish_response.data
    enabled_response = WorkflowViewSet.as_view({"post": "set_enabled"})(
        _request(factory, "post", f"/workflows/{workflow.id}/enabled/", superuser, {"enabled": True}),
        pk=workflow.id,
    )
    plan_view = WorkflowViewSet.as_view({"get": "launch_plan"})
    plan_response = plan_view(
        _request(factory, "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )
    run = WorkflowViewSet.as_view({"post": "run"})
    run_response = run(
        _request(
            factory,
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {
                "launch_token": plan_response.data["launch_token"],
                "inputs": {
                    "targets": ["node:linux-1", "node:windows-1"],
                },
            },
        ),
        pk=workflow.id,
    )

    assert publish_response.status_code == 200
    assert enabled_response.status_code == 200
    workflow.refresh_from_db()
    assert workflow.name == "生产主机健康巡检"
    assert workflow.description == "发布当前页面中的草稿"
    version = WorkflowVersion.objects.get(workflow=workflow, version=1)
    assert version.definition["name"] == workflow.engine_name
    assert version.definition["version"] == 1
    report_inputs = next(task["inputParameters"] for task in version.definition["tasks"] if task["name"] == "bklite_document_render")
    assert version.resource_snapshot["templates"] == []
    assert version.resource_snapshot["capability_profiles"] == []
    assert "required_metrics" not in version.definition["tasks"][0]["inputParameters"]
    assert report_inputs["data"] == "${scan.output}"
    assert "template" not in report_inputs
    assert run_response.status_code == 201
    assert plan_response.data["target_fields"][0]["key"] == "targets"
    execution = WorkflowExecution.objects.get()
    assert execution.input["execution_id"] == str(execution.id)
    assert execution.input["team"] == 7
    assert {target["operating_system"] for target in execution.input["targets"]} == {"linux", "windows"}
    assert execution.target_snapshot["unique_total"] == 2
    assert "report_template" not in execution.input
    assert execution.resource_snapshot["capability_profiles"] == []
    conductor.start_workflow.assert_called_once_with(
        workflow.engine_name,
        version=1,
        inputs=execution.input,
        correlation_id=str(execution.id),
    )


@pytest.mark.django_db
def test_file_upload_uses_published_field_constraints(superuser, mocker):
    metadata = build_health_inspection_canvas_metadata()
    metadata["input_schema"]["properties"]["report_template"] = {
        "type": "object",
        "title": "附件",
        "x-widget": "file-upload",
        "x-file-options": {"accept": ["docx", "xlsx"], "maxSizeMiB": 5, "maxCount": 1, "sourceModes": ["upload"]},
    }
    metadata["trigger_nodes"][0]["input_schema"] = metadata["input_schema"]
    workflow = Workflow.objects.create(
        name="文件字段流程",
        team=[7],
        definition=build_health_inspection_definition(),
        canvas_metadata=metadata,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=workflow.definition,
        canvas_metadata=metadata,
    )
    factory = APIRequestFactory()
    plan = WorkflowViewSet.as_view({"get": "launch_plan"})(
        _request(factory, "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )
    upload = WorkflowViewSet.as_view({"post": "report_template_upload"})
    store = mocker.patch("apps.workflow_orchestration.views.store_uploaded_report_template")
    store.return_value = {"kind": "uploaded", "name": "health.docx", "format": "docx", "size": 128, "token": "token"}
    request = factory.post(
        f"/workflows/{workflow.id}/report-template-upload/",
        {
            "launch_token": plan.data["launch_token"],
            "field_key": "report_template",
            "file": SimpleUploadedFile("health.docx", b"office"),
        },
        format="multipart",
    )
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=superuser)

    response = upload(request, pk=workflow.id)

    assert response.status_code == 201
    assert store.call_args.kwargs["allowed_formats"] == ("docx", "xlsx")
    assert store.call_args.kwargs["max_bytes"] == 5 * 1024 * 1024

    invalid_request = factory.post(
        f"/workflows/{workflow.id}/report-template-upload/",
        {
            "launch_token": plan.data["launch_token"],
            "field_key": "rules",
            "file": SimpleUploadedFile("health.docx", b"office"),
        },
        format="multipart",
    )
    invalid_request.COOKIES["current_team"] = "7"
    force_authenticate(invalid_request, user=superuser)
    invalid = upload(invalid_request, pk=workflow.id)
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_report_template_test_upload_is_bound_to_draft_debug_execution(superuser, mocker):
    workflow = Workflow.objects.create(
        name="文档节点测试流程",
        team=[7],
        definition=build_health_inspection_definition(),
        canvas_metadata=build_health_inspection_canvas_metadata(),
    )
    upload = WorkflowViewSet.as_view({"post": "report_template_test_upload"})
    store = mocker.patch("apps.workflow_orchestration.views.store_uploaded_report_template")
    store.return_value = {
        "kind": "uploaded",
        "name": "health.docx",
        "format": "docx",
        "size": 128,
        "placeholders": ["summary.total"],
        "token": "debug-token",
    }
    factory = APIRequestFactory()
    request = factory.post(
        f"/workflows/{workflow.id}/report-template-test-upload/",
        {"file": SimpleUploadedFile("health.docx", b"office")},
        format="multipart",
    )
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=superuser)

    response = upload(request, pk=workflow.id)

    assert response.status_code == 201
    assert response.data["placeholders"] == ["summary.total"]
    assert store.call_args.kwargs["workflow_id"] == workflow.id
    assert store.call_args.kwargs["workflow_version"] == 0
    assert store.call_args.kwargs["team"] == 7
    assert store.call_args.kwargs["allowed_formats"] == ("docx", "xlsx")


@pytest.mark.django_db
def test_agent_knowledge_upload_uses_edit_scope_and_returns_controlled_reference(superuser, mocker):
    workflow = Workflow.objects.create(name="智能体流程", team=[7], definition={}, canvas_metadata={})
    upload = WorkflowViewSet.as_view({"post": "agent_knowledge_upload"})
    store = mocker.patch("apps.workflow_orchestration.views.store_uploaded_agent_knowledge")
    store.return_value = {
        "kind": "workflow_agent_knowledge",
        "name": "runbook.md",
        "format": "md",
        "size": 32,
        "token": "signed-token",
    }
    factory = APIRequestFactory()
    request = factory.post(
        f"/workflows/{workflow.id}/agent-knowledge-upload/",
        {"file": SimpleUploadedFile("runbook.md", b"# runbook")},
        format="multipart",
    )
    request.COOKIES["current_team"] = "7"
    force_authenticate(request, user=superuser)

    response = upload(request, pk=workflow.id)

    assert response.status_code == 201
    assert response.data["kind"] == "workflow_agent_knowledge"
    assert store.call_args.kwargs == {"workflow_id": workflow.id, "team": 7}


@pytest.mark.django_db
def test_run_rejects_cross_team_or_missing_target(superuser, mocker):
    workflow = Workflow.objects.create(
        name="主机健康巡检",
        team=[7],
        definition=build_health_inspection_definition(),
        canvas_metadata=build_health_inspection_canvas_metadata(),
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    metadata = build_health_inspection_canvas_metadata()
    metadata["input_schema"] = {
        "type": "object",
        "properties": {"targets": metadata["data_contract"]["inputs"][0]["schema"]},
        "required": ["targets"],
        "additionalProperties": False,
    }
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=build_health_inspection_definition(),
        canvas_metadata=metadata,
    )
    mocker.patch("apps.workflow_orchestration.views.NodeMgmt").return_value.get_authorized_execution_targets_by_ids.return_value = []
    run = WorkflowViewSet.as_view({"post": "run"})

    plan = WorkflowViewSet.as_view({"get": "launch_plan"})(
        _request(APIRequestFactory(), "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )
    response = run(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {"launch_token": plan.data["launch_token"], "inputs": {"targets": ["node:other-team-node"]}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 403
    assert WorkflowExecution.objects.count() == 0


@pytest.mark.django_db
def test_run_rejects_unsupported_target_os_before_creating_execution(superuser, mocker):
    definition = build_health_inspection_definition()
    metadata = build_health_inspection_canvas_metadata()
    metadata["input_schema"] = {
        "type": "object",
        "properties": {"targets": metadata["data_contract"]["inputs"][0]["schema"]},
        "required": ["targets"],
        "additionalProperties": False,
    }
    workflow = Workflow.objects.create(
        name="主机健康巡检",
        team=[7],
        definition=definition,
        canvas_metadata=metadata,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=definition,
        canvas_metadata=metadata,
    )
    node_client = mocker.patch("apps.workflow_orchestration.views.NodeMgmt").return_value
    node_client.get_authorized_execution_targets_by_ids.return_value = [
        {
            "id": "aix-1",
            "name": "legacy-aix",
            "ip": "10.0.0.3",
            "operating_system": "aix",
            "active": True,
        }
    ]
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient")
    factory = APIRequestFactory()
    plan = WorkflowViewSet.as_view({"get": "launch_plan"})(
        _request(factory, "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )

    response = WorkflowViewSet.as_view({"post": "run"})(
        _request(
            factory,
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {"launch_token": plan.data["launch_token"], "inputs": {"targets": ["node:aix-1"]}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 400
    assert "aix" in response.data["detail"]
    assert WorkflowExecution.objects.count() == 0
    conductor.assert_not_called()


@pytest.mark.django_db
def test_generic_workflow_runs_with_schema_validated_inputs_without_host_targets(superuser, mocker):
    definition = {
        "name": "generic",
        "version": 1,
        "schemaVersion": 2,
        "inputParameters": ["service"],
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "passthrough",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "body": "${workflow.input.service}",
                },
            }
        ],
    }
    workflow = Workflow.objects.create(
        name="通用流程",
        team=[7],
        definition=definition,
        canvas_metadata={
            "input_schema": {
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
                "additionalProperties": False,
            }
        },
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=definition,
        canvas_metadata=workflow.canvas_metadata,
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "generic-execution-1"
    run = WorkflowViewSet.as_view({"post": "run"})

    plan = WorkflowViewSet.as_view({"get": "launch_plan"})(
        _request(APIRequestFactory(), "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )
    response = run(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {"launch_token": plan.data["launch_token"], "inputs": {"service": "billing"}},
        ),
        pk=workflow.id,
    )

    assert response.status_code == 201
    assert response.data["input"]["service"] == "billing"
    assert response.data["input"]["execution_id"] == response.data["id"]

    retry = run(
        _request(
            APIRequestFactory(),
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {"launch_token": plan.data["launch_token"], "inputs": {"service": "billing"}},
        ),
        pk=workflow.id,
    )
    assert retry.status_code == 200
    assert retry.data["id"] == response.data["id"]
    assert conductor.start_workflow.call_count == 1


@pytest.mark.django_db
def test_offline_target_requires_popconfirm_retry_and_freezes_confirmation(superuser, mocker):
    definition = build_health_inspection_definition()
    metadata = build_health_inspection_canvas_metadata()
    metadata["input_schema"] = {
        "type": "object",
        "properties": {"targets": metadata["data_contract"]["inputs"][0]["schema"]},
        "required": ["targets"],
        "additionalProperties": False,
    }
    workflow = Workflow.objects.create(
        name="离线主机巡检",
        team=[7],
        definition=definition,
        canvas_metadata=metadata,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=definition, canvas_metadata=metadata)
    node_client = mocker.patch("apps.workflow_orchestration.views.NodeMgmt").return_value
    node_client.get_authorized_execution_targets_by_ids.return_value = [
        {
            "id": "offline-1",
            "name": "offline-host",
            "ip": "10.0.0.9",
            "operating_system": "linux",
            "active": False,
        }
    ]
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    conductor.start_workflow.return_value = "conductor-offline-1"
    factory = APIRequestFactory()
    plan = WorkflowViewSet.as_view({"get": "launch_plan"})(
        _request(factory, "get", f"/workflows/{workflow.id}/launch-plan/", superuser),
        pk=workflow.id,
    )
    run = WorkflowViewSet.as_view({"post": "run"})
    payload = {"launch_token": plan.data["launch_token"], "inputs": {"targets": ["node:offline-1"]}}

    blocked = run(_request(factory, "post", f"/workflows/{workflow.id}/run/", superuser, payload), pk=workflow.id)
    started = run(
        _request(
            factory,
            "post",
            f"/workflows/{workflow.id}/run/",
            superuser,
            {**payload, "offline_confirmed": True},
        ),
        pk=workflow.id,
    )

    assert blocked.status_code == 409
    assert blocked.data["code"] == "OFFLINE_CONFIRMATION_REQUIRED"
    assert blocked.data["offline_targets"][0]["id"] == "node:offline-1"
    assert started.status_code == 201
    assert started.data["target_snapshot"]["offline_confirmed"] is True
    assert WorkflowExecution.objects.count() == 1
    conductor.start_workflow.assert_called_once()


@pytest.mark.django_db
def test_target_sources_are_independent_and_batch_match_does_not_create_hosts(superuser, mocker):
    node_client = mocker.patch("apps.workflow_orchestration.views.NodeMgmt").return_value
    node_client.node_list.return_value = {
        "count": 1,
        "nodes": [
            {
                "id": "node-1",
                "name": "linux-1",
                "ip": "10.0.0.1",
                "operating_system": "linux",
                "active": True,
            }
        ],
    }
    node_client.get_authorized_execution_targets_by_ips.return_value = node_client.node_list.return_value["nodes"]
    job_client = mocker.patch("apps.workflow_orchestration.views.JobMgmt").return_value
    job_client.list_automation_targets.return_value = {
        "result": True,
        "data": {
            "count": 1,
            "items": [
                {
                    "target_id": 8,
                    "name": "windows-1",
                    "ip": "10.0.0.8",
                    "os_type": "windows",
                }
            ],
        },
    }
    factory = APIRequestFactory()
    targets = WorkflowViewSet.as_view({"get": "targets"})
    match = WorkflowViewSet.as_view({"post": "match_targets"})

    nodes = targets(_request(factory, "get", "/workflows/targets/?source=node_mgmt", superuser))
    jobs = targets(_request(factory, "get", "/workflows/targets/?source=job_mgmt", superuser))
    matched = match(
        _request(
            factory,
            "post",
            "/workflows/targets/match/",
            superuser,
            {"source": "node_mgmt", "values": ["10.0.0.1", "10.0.0.1", "10.0.0.99"]},
        )
    )

    assert nodes.status_code == 200
    assert nodes.data["items"][0]["id"] == "node:node-1"
    assert jobs.status_code == 200
    assert jobs.data["items"][0]["id"] == "manual:8"
    assert [item["status"] for item in matched.data["results"]] == ["matched", "duplicate", "not_found"]


@pytest.mark.django_db
def test_enable_and_delete_reconcile_managed_nats_channels(
    superuser,
    mocker,
    django_capture_on_commit_callbacks,
):
    workflow = Workflow.objects.create(
        name="NATS 托管流程",
        team=[7],
        definition={},
        canvas_metadata={},
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition={}, canvas_metadata={})
    sync_managed_channels = mocker.patch("apps.workflow_orchestration.views.sync_workflow_nats_channels")
    cleanup_managed_channels = mocker.patch("apps.workflow_orchestration.views.delete_workflow_nats_channels")
    factory = APIRequestFactory()

    with django_capture_on_commit_callbacks(execute=True):
        disabled = WorkflowViewSet.as_view({"post": "set_enabled"})(
            _request(factory, "post", f"/workflows/{workflow.id}/enabled/", superuser, {"enabled": False}),
            pk=workflow.id,
        )
    with django_capture_on_commit_callbacks(execute=True):
        deleted = WorkflowViewSet.as_view({"delete": "destroy"})(
            _request(factory, "delete", f"/workflows/{workflow.id}/", superuser),
            pk=workflow.id,
        )

    assert disabled.status_code == 200
    assert deleted.status_code == 204
    sync_managed_channels.assert_called_once_with(workflow.id)
    cleanup_managed_channels.assert_called_once_with(workflow.id)


@pytest.mark.django_db
def test_soft_delete_preserves_terminal_history_and_disables_triggers(superuser):
    definition = {"tasks": [_notification_task("notify_delete")]}
    workflow = Workflow.objects.create(
        name="可删除流程",
        team=[7],
        definition=definition,
        current_version=1,
        status=Workflow.Status.PUBLISHED,
    )
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=definition)
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.SUCCEEDED,
    )
    trigger = WorkflowTrigger.objects.create(
        workflow=workflow,
        name="每日执行",
        trigger_type=WorkflowTrigger.Type.SCHEDULE,
        enabled=True,
        team=[7],
        next_run_at=timezone.now() + timedelta(days=1),
    )
    factory = APIRequestFactory()
    destroy = WorkflowViewSet.as_view({"delete": "destroy"})
    retrieve_workflow = WorkflowViewSet.as_view({"get": "retrieve"})
    retrieve_execution = WorkflowExecutionViewSet.as_view({"get": "retrieve"})

    deleted = destroy(_request(factory, "delete", f"/workflows/{workflow.id}/", superuser), pk=workflow.id)
    missing = retrieve_workflow(_request(factory, "get", f"/workflows/{workflow.id}/", superuser), pk=workflow.id)
    history = retrieve_execution(_request(factory, "get", f"/executions/{execution.id}/", superuser), pk=execution.id)

    tombstone = Workflow.all_objects.get(pk=workflow.id)
    trigger.refresh_from_db()
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert not Workflow.objects.filter(pk=workflow.id).exists()
    assert tombstone.deleted_at is not None
    assert tombstone.deleted_by == superuser.username
    assert tombstone.deleted_by_domain == superuser.domain
    assert trigger.enabled is False
    assert trigger.next_run_at is None
    assert history.status_code == 200
    assert history.data["workflow_name"] == workflow.name
    assert history.data["workflow_deleted"] is True
    assert history.data["definition_snapshot"] == {}
    audit = OperationLog.objects.get(app="workflow-orchestration", action_type="delete", target_id=str(workflow.id))
    assert audit.detail["workflow_name"] == workflow.name
    assert audit.detail["last_version"] == 1
    assert audit.detail["team"] == [7]
    assert audit.detail["disabled_trigger_count"] == 1
    assert audit.detail["trigger_summary"] == {"SCHEDULE": 1}

    recreated = Workflow.objects.create(name=workflow.name, team=[7], definition={})
    assert recreated.pk != workflow.pk


@pytest.mark.django_db
@pytest.mark.parametrize(
    "execution_status",
    [
        WorkflowExecution.Status.QUEUED,
        WorkflowExecution.Status.RUNNING,
        WorkflowExecution.Status.WAITING_APPROVAL,
        WorkflowExecution.Status.TERMINATING,
    ],
)
def test_soft_delete_rejects_every_non_terminal_execution(superuser, execution_status):
    workflow = Workflow.objects.create(name="执行中流程", team=[7], definition={})
    WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=0,
        team=[7],
        status=execution_status,
    )
    destroy = WorkflowViewSet.as_view({"delete": "destroy"})

    response = destroy(
        _request(APIRequestFactory(), "delete", f"/workflows/{workflow.id}/", superuser),
        pk=workflow.id,
    )

    workflow.refresh_from_db()
    assert response.status_code == 409
    assert "执行" in response.data["detail"]
    assert workflow.deleted_at is None


@pytest.mark.django_db
def test_historical_version_restores_only_draft_without_changing_live_version(superuser):
    workflow = Workflow.objects.create(
        name="版本隔离",
        team=[7],
        definition={"tasks": [{"name": "bklite_http", "taskReferenceName": "v2", "type": "SIMPLE"}]},
        current_version=2,
        status=Workflow.Status.PUBLISHED,
    )
    v1 = {"tasks": [_notification_task("v1")]}
    WorkflowVersion.objects.create(workflow=workflow, version=1, definition=v1, canvas_metadata={"positions": {"v1": {"x": 1, "y": 2}}})
    WorkflowVersion.objects.create(workflow=workflow, version=2, definition=workflow.definition)
    WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    versions = WorkflowViewSet.as_view({"get": "versions"})
    restore = WorkflowViewSet.as_view({"post": "restore_version_draft"})

    version_response = versions(
        _request(APIRequestFactory(), "get", f"/workflows/{workflow.id}/versions/?page_size=20", superuser),
        pk=workflow.id,
    )

    response = restore(
        _request(APIRequestFactory(), "post", f"/workflows/{workflow.id}/versions/1/restore-draft/", superuser),
        pk=workflow.id,
        version="1",
    )

    workflow.refresh_from_db()
    assert response.status_code == 200
    assert {item["version"]: item["execution_count"] for item in version_response.data["items"]} == {2: 0, 1: 1}
    assert workflow.definition == v1
    assert workflow.canvas_metadata["positions"]["v1"] == {"x": 1, "y": 2}
    assert workflow.current_version == 2
    assert workflow.status == Workflow.Status.PUBLISHED


@pytest.mark.django_db
def test_publish_records_atom_keys(superuser, mocker):
    _enable_notification()
    definition = {"tasks": [_notification_task("notify")]}
    workflow = Workflow.objects.create(
        name="原子快照",
        team=[7],
        definition=definition,
        canvas_metadata={"node_test_data": {"notify": {"sent": True}}},
    )
    publish = WorkflowViewSet.as_view({"post": "publish"})
    mocker.patch("apps.workflow_orchestration.views.ConductorClient")

    response = publish(
        _request(APIRequestFactory(), "post", f"/workflows/{workflow.id}/publish/", superuser),
        pk=workflow.id,
    )

    assert response.status_code == 200
    version = WorkflowVersion.objects.get(workflow=workflow)
    assert version.resource_snapshot["atoms"] == [{"key": "bklite_notification"}]
    assert "node_test_data" not in version.canvas_metadata
    workflow.refresh_from_db()
    assert "node_test_data" not in workflow.canvas_metadata


@pytest.mark.django_db
def test_publish_references_package_atom_by_stable_key(superuser, mocker):
    atom = AtomDefinition.objects.create(
        key="custom.summary",
        name="结果汇总",
        category="数据处理",
        description="汇总上游结果",
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
        name="自定义原子流程",
        team=[7],
        definition={"tasks": [{"name": atom.key, "taskReferenceName": "summary", "type": "SIMPLE"}]},
    )
    conductor = mocker.patch("apps.workflow_orchestration.views.ConductorClient").return_value
    publish = WorkflowViewSet.as_view({"post": "publish"})

    response = publish(
        _request(APIRequestFactory(), "post", f"/workflows/{workflow.id}/publish/", superuser),
        pk=workflow.id,
    )

    assert response.status_code == 200
    workflow_version = WorkflowVersion.objects.get(workflow=workflow, version=1)
    task = workflow_version.definition["tasks"][0]
    assert "__bklite_atom_version" not in task.get("inputParameters", {})
    assert workflow_version.resource_snapshot["atoms"] == [{"key": atom.key}]
    registered = conductor.register_task_definitions.call_args.args[0]
    assert any(item["name"] == atom.key for item in registered)


@pytest.mark.django_db
def test_execution_list_returns_all_records_and_marks_actionable_approvals(superuser):
    workflow = Workflow.objects.create(name="待审批流程", team=[7], definition={})
    mine = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.WAITING_APPROVAL,
        started_by="alice",
    )
    WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.SUCCEEDED,
        started_by="bob",
    )
    interaction = WorkflowInteraction.objects.create(
        execution=mine,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="approval",
        conductor_task_id="task-approval",
        title="发布确认",
        candidate_users=[superuser.username],
        team=[7],
    )
    view = WorkflowExecutionViewSet.as_view({"get": "list"})

    response = view(_request(APIRequestFactory(), "get", "/executions/", superuser))

    assert response.status_code == 200
    assert response.data["count"] == 2
    actionable = next(item for item in response.data["items"] if item["id"] == str(mine.id))
    assert actionable["has_warnings"] is False
    assert actionable["warning_count"] == 0
    assert actionable["pending_approval_count"] == 1
    assert actionable["actionable_approval_ids"] == [str(interaction.id)]

    count_view = WorkflowInteractionViewSet.as_view({"get": "pending_count"})
    count_response = count_view(_request(APIRequestFactory(), "get", "/interactions/pending-count/", superuser))
    assert count_response.data == {"count": 1}


@pytest.mark.django_db
def test_execution_list_mine_filter_returns_only_current_users_pending_approvals(superuser):
    workflow = Workflow.objects.create(name="待审批流程", team=[7], definition={})
    mine = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.WAITING_APPROVAL,
    )
    others = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.WAITING_APPROVAL,
    )
    WorkflowInteraction.objects.create(
        execution=mine,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="my-approval",
        conductor_task_id="task-mine",
        title="我的审批",
        candidate_users=[superuser.username],
        team=[7],
    )
    WorkflowInteraction.objects.create(
        execution=others,
        interaction_type=WorkflowInteraction.Type.APPROVAL,
        task_reference="other-approval",
        conductor_task_id="task-other",
        title="他人的审批",
        candidate_users=["someone-else"],
        team=[7],
    )
    view = WorkflowExecutionViewSet.as_view({"get": "list"})

    response = view(_request(APIRequestFactory(), "get", "/executions/?mine=1", superuser))

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["id"] == str(mine.id)


@pytest.mark.django_db
def test_execution_list_enforces_bounded_server_pagination(superuser):
    workflow = Workflow.objects.create(name="分页流程", team=[7], definition={})
    for execution_status in (
        WorkflowExecution.Status.FAILED,
        WorkflowExecution.Status.TIMED_OUT,
        WorkflowExecution.Status.SUCCEEDED,
    ):
        WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=1,
            team=[7],
            status=execution_status,
        )
    view = WorkflowExecutionViewSet.as_view({"get": "list"})

    response = view(_request(APIRequestFactory(), "get", "/executions/?page=1&page_size=2", superuser))

    assert response.data["count"] == 3
    assert len(response.data["items"]) == 2

    failed_response = view(_request(APIRequestFactory(), "get", "/executions/?status=FAILED", superuser))
    assert failed_response.data["count"] == 1

    debug = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=1,
        team=[7],
        status=WorkflowExecution.Status.SUCCEEDED,
        mode=WorkflowExecution.Mode.DEBUG,
    )
    debug_response = view(_request(APIRequestFactory(), "get", "/executions/?mode=DEBUG", superuser))
    assert debug_response.data["count"] == 1
    assert debug_response.data["items"][0]["id"] == str(debug.id)
    invalid_mode = view(_request(APIRequestFactory(), "get", "/executions/?mode=BREAKPOINT", superuser))
    assert invalid_mode.status_code == 400


@pytest.mark.django_db
def test_execution_list_filters_by_workflow_name_on_server(superuser):
    matched_workflow = Workflow.objects.create(name="主机健康巡检", team=[7], definition={})
    other_workflow = Workflow.objects.create(name="发布审批", team=[7], definition={})
    matched = WorkflowExecution.objects.create(workflow=matched_workflow, workflow_version=1, team=[7])
    WorkflowExecution.objects.create(workflow=other_workflow, workflow_version=1, team=[7])

    response = WorkflowExecutionViewSet.as_view({"get": "list"})(_request(APIRequestFactory(), "get", "/executions/?query=健康", superuser))

    assert response.data["count"] == 1
    assert response.data["items"][0]["id"] == str(matched.id)


@pytest.mark.django_db
def test_successful_artifact_download_is_audited(superuser, mocker):
    workflow = Workflow.objects.create(name="巡检", team=[7], definition={})
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    artifact = ExecutionArtifact.objects.create(
        execution=execution,
        team=[7],
        format="docx",
        object_key="workflow-orchestration/executions/report.docx",
        filename="report.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="a" * 64,
        size=6,
        expires_at=timezone.now() + timedelta(days=1),
    )
    mocker.patch("apps.workflow_orchestration.views.WorkflowObjectStore").return_value.get.return_value = (
        b"report",
        "report.docx",
        6,
    )
    audit = mocker.patch("apps.workflow_orchestration.views.log_operation")
    download = ExecutionArtifactViewSet.as_view({"get": "download"})

    response = download(
        _request(APIRequestFactory(), "get", f"/artifacts/{artifact.id}/download/", superuser),
        pk=artifact.id,
    )

    assert response.status_code == 200
    audit.assert_called_once()
    assert audit.call_args.kwargs["target_id"] == str(artifact.id)


@pytest.mark.django_db
def test_artifact_download_rejects_oversized_artifact_before_object_get(superuser, mocker):
    from apps.workflow_orchestration.services.object_store import MAX_ARTIFACT_DOWNLOAD_BYTES

    workflow = Workflow.objects.create(name="超大报告", team=[7], definition={})
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    artifact = ExecutionArtifact.objects.create(
        execution=execution,
        team=[7],
        format="docx",
        object_key="workflow-orchestration/executions/huge.docx",
        filename="huge.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="c" * 64,
        size=MAX_ARTIFACT_DOWNLOAD_BYTES + 1,
        expires_at=timezone.now() + timedelta(days=1),
    )
    store = mocker.patch("apps.workflow_orchestration.views.WorkflowObjectStore").return_value
    download = ExecutionArtifactViewSet.as_view({"get": "download"})

    response = download(
        _request(APIRequestFactory(), "get", f"/artifacts/{artifact.id}/download/", superuser),
        pk=artifact.id,
    )

    assert response.status_code == 413
    store.get.assert_not_called()


@pytest.mark.django_db
def test_shared_report_link_downloads_without_login_and_rejects_expired_tokens(mocker):
    from urllib.parse import parse_qs, urlparse

    from rest_framework.permissions import AllowAny

    from apps.workflow_orchestration.services.report_links import build_report_download_link

    workflow = Workflow.objects.create(name="巡检", team=[7], definition={})
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    artifact = ExecutionArtifact.objects.create(
        execution=execution,
        team=[7],
        format="docx",
        object_key="workflow-orchestration/executions/report.docx",
        filename="report.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256="b" * 64,
        size=6,
        expires_at=timezone.now() + timedelta(days=1),
    )
    mocker.patch("apps.workflow_orchestration.views.WorkflowObjectStore").return_value.get.return_value = (
        b"report",
        "report.docx",
        6,
    )
    audit = mocker.patch("apps.workflow_orchestration.views.log_operation")
    link = build_report_download_link(artifact_id=str(artifact.id), execution_id=str(execution.id), team=7)
    token = parse_qs(urlparse(link).query)["token"][0]
    shared = ExecutionArtifactViewSet.as_view(
        {"get": "shared"},
        permission_classes=[AllowAny],
        authentication_classes=[],
    )

    response = shared(APIRequestFactory().get("/artifacts/shared/", {"token": token}))

    assert response.status_code == 200
    assert response["X-Content-Type-Options"] == "nosniff"
    audit.assert_not_called()
    expired = shared(APIRequestFactory().get("/artifacts/shared/?token=not-a-token"))
    assert expired.status_code == 403

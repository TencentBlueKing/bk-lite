from __future__ import annotations

import copy
import re
from datetime import datetime, time, timedelta
from io import BytesIO

from django.db import IntegrityError, transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Q, Subquery, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import workflow_orchestration_logger as logger
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import AuthViewSet, build_json_membership_query
from apps.rpc.job_mgmt import JobMgmt
from apps.rpc.node_mgmt import NodeMgmt
from apps.system_mgmt.utils.operation_log_utils import log_operation
from apps.workflow_orchestration.models import (
    AtomConfigTemplate,
    AtomDefinition,
    ExecutionArtifact,
    Workflow,
    WorkflowExecution,
    WorkflowInteraction,
    WorkflowTrigger,
    WorkflowVersion,
)
from apps.workflow_orchestration.permissions import filter_workflow_queryset
from apps.workflow_orchestration.serializers import (
    WORKFLOW_NAME_CONFLICT_MESSAGE,
    AtomConfigTemplateSerializer,
    AtomDefinitionSerializer,
    AtomDefinitionSummarySerializer,
    NatsTestListenRequestSerializer,
    NatsTestSessionRequestSerializer,
    SchedulePreviewRequestSerializer,
    WebhookTestListenRequestSerializer,
    WebhookTestSessionRequestSerializer,
    WorkflowDashboardApprovalSerializer,
    WorkflowDuplicateRequestSerializer,
    WorkflowExecutionListSerializer,
    WorkflowExecutionSerializer,
    WorkflowInteractionSerializer,
    WorkflowSerializer,
    WorkflowTriggerSerializer,
    WorkflowVersionSerializer,
)
from apps.workflow_orchestration.services.agent_knowledge_inputs import store_uploaded_agent_knowledge
from apps.workflow_orchestration.services.atom_registry import available_atom_catalog, ensure_platform_atom, task_definition_from_catalog_item
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS, atom_catalog_payload, system_node_catalog_payload
from apps.workflow_orchestration.services.capability_profiles import capability_resource_snapshot
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.data_contracts import validate_and_compile_workflow_data_contract
from apps.workflow_orchestration.services.definitions import (
    DefinitionValidationError,
    build_blank_canvas_metadata,
    build_blank_definition,
    build_health_inspection_canvas_metadata,
    build_health_inspection_definition,
    compile_disabled_nodes,
    prepare_definition_for_publish,
    validate_conductor_definition,
    validate_workflow_inputs,
)
from apps.workflow_orchestration.services.execution_details import build_execution_node_detail, build_execution_node_summary
from apps.workflow_orchestration.services.executions import apply_remote_execution
from apps.workflow_orchestration.services.graph_compiler import compile_canvas_graph
from apps.workflow_orchestration.services.interactions import InteractionConflict, InteractionForbidden, decide_interaction
from apps.workflow_orchestration.services.launch_plans import (
    LaunchPlanTokenError,
    build_launch_plan,
    extract_target_fields,
    launch_token_digest,
    verify_launch_token,
)
from apps.workflow_orchestration.services.managed_nats_channels import delete_workflow_nats_channels, sync_workflow_nats_channels
from apps.workflow_orchestration.services.nats_test_sessions import (
    NatsTestSessionError,
    NatsTestTimeout,
    create_nats_test_session,
    read_nats_test_session,
    wait_for_nats_test_event,
)
from apps.workflow_orchestration.services.object_store import MAX_ARTIFACT_DOWNLOAD_BYTES, ArtifactTooLarge, WorkflowObjectStore
from apps.workflow_orchestration.services.orchestration_contract import validate_orchestration_metadata
from apps.workflow_orchestration.services.report_links import read_report_download_link
from apps.workflow_orchestration.services.report_template_inputs import freeze_document_templates, store_uploaded_report_template
from apps.workflow_orchestration.services.reports import ReportTemplateError
from apps.workflow_orchestration.services.runtime import start_debug_execution, start_execution
from apps.workflow_orchestration.services.schedules import bind_schedule_timezones, build_schedule_preview, resolve_user_timezone
from apps.workflow_orchestration.services.target_resolver import (
    RpcTargetGateway,
    TargetDependencyUnavailable,
    TargetResolutionError,
    resolve_target_fields,
)
from apps.workflow_orchestration.services.triggers import TriggerConflict, invoke_trigger, sync_published_triggers
from apps.workflow_orchestration.services.webhook_test_sessions import (
    WebhookTestSessionError,
    WebhookTestTimeout,
    create_webhook_test_session,
    read_webhook_test_session,
    wait_for_webhook_test_event,
)
from apps.workflow_orchestration.services.workflow_projections import workflow_trigger_types
from apps.workflow_orchestration.services.workflows import WorkflowDeleteConflict, soft_delete_workflow
from apps.workflow_orchestration.utils.i18n import workflow_message

APP_NAME = "workflow-orchestration"


class WorkflowPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({"count": self.page.paginator.count, "items": data})


def _identity(request):
    return getattr(request.user, "username", ""), getattr(request.user, "domain", "domain.com")


def _team_id(request) -> int:
    value = get_current_team(request)
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(workflow_message(request, "message.invalid_current_team", "缺少或非法的 current_team")) from error


def _permission_data(request, team: int) -> dict:
    username, domain = _identity(request)
    return {
        "username": username,
        "domain": domain,
        "current_team": team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": bool(getattr(request.user, "is_superuser", False)),
    }


def _audit(request, action_type: str, summary: str, *, target_type: str, target_id, detail=None) -> None:
    log_operation(
        request,
        action_type,
        APP_NAME,
        summary,
        target_type=target_type,
        target_id=str(target_id),
        detail=detail,
    )


def _workflow_name_conflict_response():
    return Response(
        {"name": [WORKFLOW_NAME_CONFLICT_MESSAGE]},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _is_workflow_name_conflict(error: IntegrityError) -> bool:
    cause = getattr(error, "__cause__", None)
    diagnostics = getattr(cause, "diag", None)
    constraint_name = getattr(diagnostics, "constraint_name", "")
    return constraint_name == "uq_workflow_active_name_team" or "uq_workflow_active_name_team" in str(error)


def _contains_atom(definition, atom_name: str) -> bool:
    return any(task.get("name") == atom_name for task in _walk_definition_tasks(definition.get("tasks") or []))


def _walk_definition_tasks(tasks):
    for task in tasks:
        if not isinstance(task, dict):
            continue
        yield task
        for key in ("loopOver", "defaultCase"):
            nested = task.get(key)
            if isinstance(nested, list):
                yield from _walk_definition_tasks(nested)
        for branch in (task.get("decisionCases") or {}).values():
            if isinstance(branch, list):
                yield from _walk_definition_tasks(branch)
        for branch in task.get("forkTasks", []) or []:
            if isinstance(branch, list):
                yield from _walk_definition_tasks(branch)


def _debug_definition(definition, *, task_reference, node_inputs, confirmed, atom_catalog):
    candidate = copy.deepcopy(definition)
    if task_reference:
        task = next(
            (item for item in _walk_definition_tasks(candidate.get("tasks") or []) if item.get("taskReferenceName") == task_reference),
            None,
        )
        if task is None or task.get("type") != "SIMPLE":
            raise ValueError("单节点测试只支持已注册的 SIMPLE 原子")
        atom = atom_catalog.get(task.get("name")) or {}
        if atom.get("safety_level", "MUTATION") != "READ_ONLY" and confirmed is not True:
            raise ValueError("该原子可能产生真实副作用，单节点测试必须二次确认")
        if node_inputs is not None:
            if not isinstance(node_inputs, dict):
                raise ValueError("node_inputs 必须是 JSON 对象")
            task["inputParameters"] = copy.deepcopy(node_inputs)
        candidate["tasks"] = [task]
        candidate["outputParameters"] = {"result": f"${{{task['taskReferenceName']}.output}}"}
    return candidate


def _node_debug_input_schema(schema, inputs, *, task_reference):
    if not task_reference or not isinstance(schema, dict) or not isinstance(inputs, dict):
        return schema
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    included = {key for key in inputs if key in properties}
    return {
        **copy.deepcopy(schema),
        "properties": {key: copy.deepcopy(value) for key, value in properties.items() if key in included},
        "required": [key for key in schema.get("required", []) if key in included],
    }


def _node_target(node):
    source_id = str(node["id"])
    return {
        **node,
        "id": f"node:{source_id}",
        "source": "node_mgmt",
        "source_id": source_id,
        "connected": node.get("active") if isinstance(node.get("active"), bool) else None,
    }


def _manual_target(target):
    source_id = int(target["target_id"])
    return {
        "id": f"manual:{source_id}",
        "source": "job_mgmt",
        "source_id": source_id,
        "name": target.get("name", ""),
        "ip": target.get("ip", ""),
        "operating_system": target.get("os_type", ""),
        "cloud_region_id": target.get("cloud_region_id"),
        "connected": None,
    }


class WorkflowViewSet(AuthViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    ORGANIZATION_FIELD = "team"
    pagination_class = WorkflowPageNumberPagination

    def _scoped_queryset(self, request, *, require_operate=False):
        team = self._validate_current_team_permission(request)
        return filter_workflow_queryset(request, self.get_queryset(), team, require_operate=require_operate)

    def _scoped_object(self, request, *, require_operate=False):
        return get_object_or_404(
            self._scoped_queryset(request, require_operate=require_operate),
            pk=self.kwargs.get("pk"),
        )

    def _validated_request_draft(self, request, workflow, *, include_metadata=False):
        allowed_fields = {"definition", "canvas_metadata"}
        if include_metadata:
            allowed_fields.update({"name", "description"})
        payload = {key: request.data[key] for key in allowed_fields if key in request.data}
        if not payload:
            return workflow.definition, workflow.canvas_metadata, workflow.name, workflow.description
        serializer = self.get_serializer(workflow, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        return (
            values.get("definition", workflow.definition),
            values.get("canvas_metadata", workflow.canvas_metadata),
            values.get("name", workflow.name),
            values.get("description", workflow.description),
        )

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        latest_execution = WorkflowExecution.objects.filter(workflow_id=OuterRef("pk")).order_by("-created_at")
        queryset = (
            self.filter_queryset(self._scoped_queryset(request))
            .annotate(
                recent_execution_status=Subquery(latest_execution.values("status")[:1]),
                recent_execution_at=Subquery(latest_execution.values("created_at")[:1]),
            )
            .prefetch_related(
                Prefetch(
                    "triggers",
                    queryset=WorkflowTrigger.objects.only("workflow_id", "trigger_type"),
                    to_attr="trigger_definitions",
                )
            )
        )
        if request.query_params.get("query"):
            query = request.query_params["query"][:120]
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))
        list_status = str(request.query_params.get("status") or "").upper()
        if list_status == "DRAFT":
            queryset = queryset.filter(current_version=0)
        elif list_status == "PUBLISHED":
            queryset = queryset.filter(current_version__gt=0)
        elif list_status:
            return Response({"detail": "status 非法"}, status=status.HTTP_400_BAD_REQUEST)
        enabled_filter = str(request.query_params.get("enabled") or "").strip().lower()
        if enabled_filter in {"true", "false"}:
            queryset = queryset.filter(current_version__gt=0, enabled=enabled_filter == "true")
        elif enabled_filter:
            return Response({"detail": "enabled 非法"}, status=status.HTTP_400_BAD_REQUEST)
        trigger_type = str(request.query_params.get("trigger_type") or "").upper()
        if trigger_type:
            if trigger_type not in WorkflowTrigger.Type.values:
                return Response({"detail": "trigger_type 非法"}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(build_json_membership_query(queryset, "trigger_types", [trigger_type]))
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self._scoped_object(request)).data)

    @HasPermission("workflow-Add", app_name=APP_NAME)
    def create(self, request, *args, **kwargs):
        team = self._validate_current_team_permission(request)
        payload = request.data.copy()
        starter = payload.pop("starter", "health_inspection")
        if not payload.get("definition"):
            payload["definition"] = build_blank_definition() if starter == "blank" else build_health_inspection_definition()
        if not payload.get("canvas_metadata"):
            payload["canvas_metadata"] = build_blank_canvas_metadata() if starter == "blank" else build_health_inspection_canvas_metadata()
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        username, domain = _identity(request)
        try:
            workflow = serializer.save(
                team=[team],
                created_by=username,
                updated_by=username,
                domain=domain,
                updated_by_domain=domain,
            )
        except IntegrityError as error:
            if _is_workflow_name_conflict(error):
                return _workflow_name_conflict_response()
            raise
        _audit(request, "create", "新建流程草稿", target_type="workflow", target_id=workflow.id)
        return Response(self.get_serializer(workflow).data, status=status.HTTP_201_CREATED)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def partial_update(self, request, *args, **kwargs):
        scoped = self._scoped_object(request, require_operate=True)
        supplied_revision = request.data.get("draft_revision")
        try:
            with transaction.atomic():
                workflow = Workflow.objects.select_for_update().get(pk=scoped.pk)
                if supplied_revision is not None and supplied_revision != workflow.draft_revision:
                    return Response(
                        {
                            "detail": "草稿已经被其他修改更新，请重新载入后再保存",
                            "code": "DRAFT_REVISION_CONFLICT",
                            "draft_revision": workflow.draft_revision,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                payload = {key: value for key, value in request.data.items() if key != "draft_revision"}
                serializer = self.get_serializer(workflow, data=payload, partial=True)
                serializer.is_valid(raise_exception=True)
                username, domain = _identity(request)
                serializer.save(
                    updated_by=username,
                    updated_by_domain=domain,
                    draft_revision=workflow.draft_revision + 1,
                    draft_base_version=workflow.draft_base_version or workflow.current_version,
                    has_draft=True,
                )
        except IntegrityError as error:
            if _is_workflow_name_conflict(error):
                return _workflow_name_conflict_response()
            raise
        _audit(request, "update", "保存流程草稿", target_type="workflow", target_id=workflow.id)
        return Response(self.get_serializer(workflow).data)

    @action(methods=["POST"], detail=True, url_path="enabled")
    @HasPermission("workflow-Publish", app_name=APP_NAME)
    def set_enabled(self, request, pk=None):
        scoped = self._scoped_object(request, require_operate=True)
        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response({"detail": "enabled 必须是布尔值"}, status=status.HTTP_400_BAD_REQUEST)
        if enabled and not scoped.current_version:
            return Response({"detail": "请先发布流程"}, status=status.HTTP_409_CONFLICT)
        if enabled:
            version = scoped.versions.filter(version=scoped.current_version).first()
            if version is None:
                return Response({"detail": "当前发布版本不存在"}, status=status.HTTP_409_CONFLICT)
            try:
                validate_conductor_definition(
                    version.definition,
                    atom_catalog=available_atom_catalog(_team_id(request)),
                )
            except DefinitionValidationError as error:
                return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        username, domain = _identity(request)
        scoped.enabled = enabled
        scoped.updated_by = username
        scoped.updated_by_domain = domain
        scoped.save(update_fields=("enabled", "updated_by", "updated_by_domain", "updated_at"))
        trigger_updates = {"enabled": enabled}
        if not enabled:
            trigger_updates["next_run_at"] = None
        scoped.triggers.update(**trigger_updates)
        if enabled:
            version = scoped.versions.get(version=scoped.current_version)
            sync_published_triggers(scoped, version.canvas_metadata, username=username, domain=domain)
        transaction.on_commit(lambda workflow_id=scoped.pk: sync_workflow_nats_channels(workflow_id))
        _audit(
            request,
            "enable" if enabled else "disable",
            "启用流程" if enabled else "停用流程",
            target_type="workflow",
            target_id=scoped.id,
        )
        return Response(self.get_serializer(scoped).data)

    @HasPermission("workflow-Delete", app_name=APP_NAME)
    def destroy(self, request, *args, **kwargs):
        workflow = self._scoped_object(request, require_operate=True)
        username, domain = _identity(request)
        try:
            deleted, audit_detail = soft_delete_workflow(
                workflow.pk,
                deleted_by=username,
                deleted_by_domain=domain,
            )
        except WorkflowDeleteConflict as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except Workflow.DoesNotExist:
            return Response({"detail": "流程不存在"}, status=status.HTTP_404_NOT_FOUND)
        transaction.on_commit(lambda workflow_id=workflow.pk: delete_workflow_nats_channels(workflow_id))
        _audit(
            request,
            "delete",
            f"删除流程“{deleted.name}” v{deleted.current_version}，停用 {audit_detail['disabled_trigger_count']} 个触发器",
            target_type="workflow",
            target_id=deleted.id,
            detail=audit_detail,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Add", app_name=APP_NAME)
    def duplicate(self, request, pk=None):
        source = self._scoped_object(request)
        request_serializer = WorkflowDuplicateRequestSerializer(
            data={"name": request.data.get("name", f"{source.name[:116]}（副本）")},
            context={"team": source.team},
        )
        request_serializer.is_valid(raise_exception=True)
        username, domain = _identity(request)
        try:
            copied = Workflow.objects.create(
                name=request_serializer.validated_data["name"],
                description=source.description,
                team=source.team,
                definition=copy.deepcopy(source.definition),
                canvas_metadata=copy.deepcopy(source.canvas_metadata),
                created_by=username,
                updated_by=username,
                domain=domain,
                updated_by_domain=domain,
            )
        except IntegrityError as error:
            if _is_workflow_name_conflict(error):
                return _workflow_name_conflict_response()
            raise
        return Response(self.get_serializer(copied).data, status=status.HTTP_201_CREATED)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def validate(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        try:
            draft_definition, draft_metadata, _, _ = self._validated_request_draft(request, workflow)
            draft_metadata = validate_orchestration_metadata(
                draft_metadata,
                task_references={
                    task.get("taskReferenceName")
                    for task in _walk_definition_tasks(draft_definition.get("tasks") or [])
                    if isinstance(task.get("taskReferenceName"), str)
                },
            )
            catalog = available_atom_catalog(_team_id(request))
            executable_definition = compile_disabled_nodes(compile_canvas_graph(draft_definition, draft_metadata), draft_metadata)
            definition, compiled_metadata = validate_and_compile_workflow_data_contract(
                executable_definition,
                draft_metadata,
                atom_catalog=catalog,
                strict=True,
            )
            extract_target_fields(compiled_metadata)
            validate_conductor_definition(
                definition,
                atom_catalog=catalog,
            )
        except (DefinitionValidationError, ValueError) as error:
            issue = {"message": str(error), "code": "workflow_invalid"}
            return Response({"valid": False, "errors": [str(error)], "issues": [issue]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"valid": True, "errors": [], "issues": []})

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Publish", app_name=APP_NAME)
    def publish(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        supplied_revision = request.data.get("draft_revision")
        if supplied_revision is not None and supplied_revision != workflow.draft_revision:
            return Response(
                {
                    "detail": "草稿已经被其他修改更新，请重新载入后再发布",
                    "code": "DRAFT_REVISION_CONFLICT",
                    "draft_revision": workflow.draft_revision,
                },
                status=status.HTTP_409_CONFLICT,
            )
        draft_definition, draft_metadata, draft_name, draft_description = self._validated_request_draft(
            request,
            workflow,
            include_metadata=True,
        )
        next_version = workflow.current_version + 1
        team = _team_id(request)
        catalog = available_atom_catalog(team)
        try:
            draft_metadata = validate_orchestration_metadata(
                draft_metadata,
                task_references={
                    task.get("taskReferenceName")
                    for task in _walk_definition_tasks(draft_definition.get("tasks") or [])
                    if isinstance(task.get("taskReferenceName"), str)
                },
            )
            executable_definition = compile_disabled_nodes(compile_canvas_graph(draft_definition, draft_metadata), draft_metadata)
            compiled_definition, compiled_metadata = validate_and_compile_workflow_data_contract(
                executable_definition,
                draft_metadata,
                atom_catalog=catalog,
                strict=True,
            )
            extract_target_fields(compiled_metadata)
            definition = freeze_document_templates(
                prepare_definition_for_publish(
                    compiled_definition,
                    engine_name=workflow.engine_name,
                    version=next_version,
                    atom_catalog=catalog,
                )
            )
            compiled_metadata = bind_schedule_timezones(
                compiled_metadata,
                timezone_name=resolve_user_timezone(request.user),
            )
        except (DefinitionValidationError, ValueError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        resource_snapshot = {
            "templates": [],
            "required_metrics": [],
            "atoms": [],
            "capability_profiles": capability_resource_snapshot(definition, catalog),
        }
        atom_keys = sorted({task.get("name") for task in _walk_definition_tasks(definition.get("tasks") or []) if task.get("type") == "SIMPLE"})
        resource_snapshot["atoms"] = [{"key": key} for key in atom_keys if key in catalog]
        published_metadata = copy.deepcopy(compiled_metadata)
        published_metadata.pop("node_test_data", None)
        username, domain = _identity(request)
        try:
            for key in atom_keys:
                item = catalog[key]
                if item.get("source_type") == AtomDefinition.SourceType.PLATFORM:
                    ensure_platform_atom(
                        item,
                        username=username,
                        domain=domain,
                    )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        static_task_names = {item["name"] for item in TASK_DEFINITIONS}
        client = ConductorClient()
        try:
            custom_task_definitions = [task_definition_from_catalog_item(catalog[key]) for key in atom_keys if key not in static_task_names]
            client.register_task_definitions([*TASK_DEFINITIONS, *custom_task_definitions])
            client.register_workflow(definition)
        except ConductorUnavailable as error:
            logger.warning("Conductor publish unavailable workflow_id=%s", workflow.pk)
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        with transaction.atomic():
            workflow = Workflow.all_objects.select_for_update().get(pk=workflow.pk)
            if workflow.deleted_at is not None:
                return Response({"detail": "流程已删除"}, status=status.HTTP_409_CONFLICT)
            if supplied_revision is not None and supplied_revision != workflow.draft_revision:
                return Response(
                    {"detail": "草稿版本已变化，本次发布已取消", "code": "DRAFT_REVISION_CONFLICT"},
                    status=status.HTTP_409_CONFLICT,
                )
            package_keys = atom_keys
            locked_package_atoms = {atom.key: atom for atom in AtomDefinition.objects.select_for_update().filter(key__in=package_keys)}
            if set(locked_package_atoms) != set(package_keys):
                return Response(
                    {"detail": "流程引用的原子状态或版本已经变化，请刷新后重试"},
                    status=status.HTTP_409_CONFLICT,
                )
            WorkflowVersion.objects.create(
                workflow=workflow,
                version=next_version,
                definition=definition,
                canvas_metadata=published_metadata,
                resource_snapshot=resource_snapshot,
                change_summary={"atoms": atom_keys},
                created_by=username,
                domain=domain,
            )
            workflow.current_version = next_version
            workflow.status = Workflow.Status.PUBLISHED
            workflow.has_draft = False
            workflow.draft_base_version = next_version
            workflow.draft_revision += 1
            workflow.name = draft_name
            workflow.description = draft_description
            workflow.definition = draft_definition
            workflow.canvas_metadata = published_metadata
            workflow.trigger_types = workflow_trigger_types(published_metadata)
            workflow.updated_by = username
            workflow.updated_by_domain = domain
            workflow.save(
                update_fields=(
                    "name",
                    "description",
                    "definition",
                    "canvas_metadata",
                    "trigger_types",
                    "current_version",
                    "status",
                    "has_draft",
                    "draft_base_version",
                    "draft_revision",
                    "updated_by",
                    "updated_by_domain",
                    "updated_at",
                )
            )
            sync_published_triggers(workflow, published_metadata, username=username, domain=domain)
            transaction.on_commit(lambda workflow_id=workflow.pk: sync_workflow_nats_channels(workflow_id))
        _audit(request, "publish", f"发布流程 v{next_version}", target_type="workflow", target_id=workflow.id)
        return Response(self.get_serializer(workflow).data)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def debug(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        if request.data.get("breakpoint_before"):
            return Response(
                {"detail": "MVP 不支持断点调试"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            draft_definition, draft_metadata, _, _ = self._validated_request_draft(request, workflow)
            draft_metadata = validate_orchestration_metadata(
                draft_metadata,
                task_references={
                    task.get("taskReferenceName")
                    for task in _walk_definition_tasks(draft_definition.get("tasks") or [])
                    if isinstance(task.get("taskReferenceName"), str)
                },
            )
            catalog = available_atom_catalog(_team_id(request))
            executable_definition = compile_disabled_nodes(compile_canvas_graph(draft_definition, draft_metadata), draft_metadata)
            task_reference = str(request.data.get("task_reference") or "")[:100]
            debug_definition = _debug_definition(
                executable_definition,
                task_reference=task_reference,
                node_inputs=request.data.get("node_inputs"),
                confirmed=request.data.get("confirmed") is True,
                atom_catalog=catalog,
            )
            compiled_definition, compiled_metadata = validate_and_compile_workflow_data_contract(
                debug_definition,
                draft_metadata,
                atom_catalog=catalog,
                strict=True,
            )
            trigger_nodes = compiled_metadata.get("trigger_nodes") or []
            requested_trigger_id = str(request.data.get("trigger_id") or "")
            selected_trigger = next(
                (item for item in trigger_nodes if item.get("id") == requested_trigger_id),
                None,
            )
            if requested_trigger_id and selected_trigger is None:
                raise ValueError("调试触发器不存在")
            if selected_trigger is None and trigger_nodes:
                selected_trigger = next(
                    (item for item in trigger_nodes if item.get("trigger_type") == WorkflowTrigger.Type.FORM),
                    trigger_nodes[0],
                )
            trigger_type = str((selected_trigger or {}).get("trigger_type") or WorkflowTrigger.Type.FORM)
            trigger_id = str((selected_trigger or {}).get("id") or "debug-form")
            raw_inputs = copy.deepcopy(request.data.get("inputs") or {})
            input_schema = (selected_trigger or {}).get("input_schema") or compiled_metadata.get("input_schema") or {}
            inputs = validate_workflow_inputs(
                raw_inputs,
                _node_debug_input_schema(input_schema, raw_inputs, task_reference=task_reference),
            )
            username, domain = _identity(request)
            execution = start_debug_execution(
                workflow,
                inputs=inputs,
                started_by=username,
                domain=domain,
                client=ConductorClient(),
                definition_override=compiled_definition,
                canvas_metadata_override=compiled_metadata,
                debug_kind=WorkflowExecution.DebugKind.NODE if task_reference else WorkflowExecution.DebugKind.FULL,
                debug_task_reference=task_reference,
                trigger_type=trigger_type,
                trigger_id=trigger_id,
            )
        except (DefinitionValidationError, ValueError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        _audit(request, "debug", "启动流程草稿调试", target_type="execution", target_id=execution.id)
        return Response(
            WorkflowExecutionSerializer(execution, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(methods=["GET"], detail=True, url_path="launch-plan")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def launch_plan(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        if not workflow.enabled:
            return Response({"detail": "流程已停用"}, status=status.HTTP_409_CONFLICT)
        if not workflow.current_version:
            return Response({"detail": "请先发布流程"}, status=status.HTTP_409_CONFLICT)
        version = WorkflowVersion.objects.filter(workflow=workflow, version=workflow.current_version).first()
        if version is None:
            return Response({"detail": "当前生效版本不存在"}, status=status.HTTP_409_CONFLICT)
        username, domain = _identity(request)
        try:
            target_fields = extract_target_fields(version.canvas_metadata)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(
            build_launch_plan(
                workflow_id=workflow.pk,
                workflow_name=workflow.name,
                workflow_version=version.version,
                canvas_metadata=version.canvas_metadata,
                team=_team_id(request),
                username=username,
                domain=domain,
                target_fields=target_fields,
            )
        )

    @action(methods=["POST"], detail=True, url_path="agent-knowledge-upload")
    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def agent_knowledge_upload(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "请选择要上传的文件"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            reference = store_uploaded_agent_knowledge(
                uploaded_file,
                workflow_id=workflow.pk,
                team=_team_id(request),
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            safe_error = RuntimeError("workflow agent knowledge upload failed")
            logger.error(
                "event=workflow_agent_knowledge_upload_failed workflow_id=%s failed_stage=object_store error_type=%s",
                workflow.pk,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
            return Response({"detail": "知识文件存储暂不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        _audit(request, "upload", "上传智能体知识文件", target_type="workflow", target_id=workflow.pk)
        return Response(reference, status=status.HTTP_201_CREATED)

    @action(methods=["POST"], detail=True, url_path="report-template-upload")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def report_template_upload(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        if not workflow.enabled or not workflow.current_version:
            return Response({"detail": "只有已启用的已发布流程可以上传运行模板"}, status=status.HTTP_409_CONFLICT)
        team = _team_id(request)
        username, domain = _identity(request)
        try:
            launch_context = verify_launch_token(
                request.data.get("launch_token"),
                workflow_id=workflow.pk,
                team=team,
                username=username,
                domain=domain,
            )
        except LaunchPlanTokenError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        if workflow.current_version != launch_context["workflow_version"]:
            return Response({"detail": "流程生效版本已变化，请重新打开执行窗口"}, status=status.HTTP_409_CONFLICT)
        version = WorkflowVersion.objects.filter(workflow=workflow, version=workflow.current_version).first()
        field_key = str(request.data.get("field_key") or "")
        input_schema = version.canvas_metadata.get("input_schema", {}) if version and isinstance(version.canvas_metadata, dict) else {}
        field_schema = (input_schema.get("properties") or {}).get(field_key) if isinstance(input_schema, dict) else None
        if not isinstance(field_schema, dict) or field_schema.get("x-widget") != "file-upload":
            return Response({"detail": "上传字段不存在或不是文件上传字段"}, status=status.HTTP_400_BAD_REQUEST)
        file_options = field_schema.get("x-file-options") if isinstance(field_schema.get("x-file-options"), dict) else {}
        source_modes = file_options.get("sourceModes") if isinstance(file_options.get("sourceModes"), list) else []
        if "upload" not in source_modes:
            return Response({"detail": "该字段不允许上传文件"}, status=status.HTTP_400_BAD_REQUEST)
        allowed_formats = tuple(str(item).lower() for item in file_options.get("accept", []) if isinstance(item, str))
        if not allowed_formats:
            return Response({"detail": "该字段没有配置允许的文件类型"}, status=status.HTTP_409_CONFLICT)
        max_size_mib = file_options.get("maxSizeMiB", 5)
        if isinstance(max_size_mib, bool) or not isinstance(max_size_mib, (int, float)) or not 0 < max_size_mib <= 5:
            return Response({"detail": "该字段的文件大小配置非法"}, status=status.HTTP_409_CONFLICT)
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "请选择要上传的文件"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            reference = store_uploaded_report_template(
                uploaded_file,
                workflow_id=workflow.pk,
                workflow_version=workflow.current_version,
                team=team,
                username=username,
                domain=domain,
                allowed_formats=allowed_formats,
                max_bytes=int(max_size_mib * 1024 * 1024),
            )
        except (ReportTemplateError, ValueError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            safe_error = RuntimeError("workflow report template upload failed")
            logger.error(
                "event=workflow_report_template_upload_failed workflow_id=%s failed_stage=object_store error_type=%s",
                workflow.pk,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
            return Response({"detail": "报告模板存储暂不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(reference, status=status.HTTP_201_CREATED)

    @action(methods=["POST"], detail=True, url_path="report-template-test-upload")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def report_template_test_upload(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            return Response({"detail": "请选择要上传的文件"}, status=status.HTTP_400_BAD_REQUEST)
        team = _team_id(request)
        username, domain = _identity(request)
        try:
            reference = store_uploaded_report_template(
                uploaded_file,
                workflow_id=workflow.pk,
                workflow_version=0,
                team=team,
                username=username,
                domain=domain,
                allowed_formats=("docx", "xlsx"),
                max_bytes=5 * 1024 * 1024,
            )
        except (ReportTemplateError, ValueError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as error:
            safe_error = RuntimeError("workflow report test template upload failed")
            logger.error(
                "event=workflow_report_test_template_upload_failed workflow_id=%s failed_stage=object_store error_type=%s",
                workflow.pk,
                type(error).__name__,
                exc_info=(type(safe_error), safe_error, error.__traceback__),
            )
            return Response({"detail": "报告模板存储暂不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(reference, status=status.HTTP_201_CREATED)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def run(self, request, pk=None):
        workflow = self._scoped_object(request, require_operate=True)
        if not workflow.enabled:
            return Response({"detail": "流程已停用"}, status=status.HTTP_409_CONFLICT)
        team = _team_id(request)
        username, domain = _identity(request)
        launch_token = request.data.get("launch_token")
        try:
            launch_context = verify_launch_token(
                launch_token,
                workflow_id=workflow.pk,
                team=team,
                username=username,
                domain=domain,
            )
        except LaunchPlanTokenError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        if launch_context.get("parent_execution_id") is not None:
            return Response({"detail": "重新执行凭证不能用于流程列表执行"}, status=status.HTTP_409_CONFLICT)
        if workflow.current_version != launch_context["workflow_version"]:
            return Response({"detail": "流程生效版本已变化，请重新打开执行窗口"}, status=status.HTTP_409_CONFLICT)
        version = WorkflowVersion.objects.filter(
            workflow=workflow,
            version=launch_context["workflow_version"],
        ).first()
        if version is None:
            return Response({"detail": "启动凭证对应的流程版本不存在"}, status=status.HTTP_409_CONFLICT)
        try:
            inputs = validate_workflow_inputs(
                copy.deepcopy(request.data.get("inputs") or {}),
                version.canvas_metadata.get("input_schema") or {},
            )
            target_fields = extract_target_fields(version.canvas_metadata)
            target_snapshot = {}
            if target_fields:
                resolution = resolve_target_fields(
                    inputs,
                    target_fields,
                    gateway=RpcTargetGateway(
                        team=team,
                        permission_data=_permission_data(request, team),
                        node_client=NodeMgmt(is_local_client=True),
                        job_client=JobMgmt(is_local_client=True),
                    ),
                )
                if resolution.offline_targets and request.data.get("offline_confirmed") is not True:
                    return Response(
                        {
                            "detail": f"{len(resolution.offline_targets)} 台主机当前离线，需要二次确认",
                            "code": "OFFLINE_CONFIRMATION_REQUIRED",
                            "offline_targets": resolution.offline_targets,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                inputs = resolution.inputs
                target_snapshot = resolution.snapshot
                target_snapshot["offline_confirmed"] = bool(resolution.offline_targets)
        except TargetResolutionError as error:
            response_status = status.HTTP_403_FORBIDDEN if "不存在或无权访问" in str(error) else status.HTTP_400_BAD_REQUEST
            return Response({"detail": str(error)}, status=response_status)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TargetDependencyUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        try:
            execution = start_execution(
                workflow,
                inputs=inputs,
                started_by=username,
                domain=domain,
                client=ConductorClient(),
                version_number=version.version,
                launch_token_hash=launch_token_digest(launch_token),
                target_snapshot=target_snapshot,
            )
        except (ValueError, WorkflowVersion.DoesNotExist) as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        reused = bool(getattr(execution, "_launch_reused", False))
        if not reused:
            _audit(request, "execute", "启动已发布流程", target_type="execution", target_id=execution.id)
        return Response(
            WorkflowExecutionSerializer(execution, context={"request": request}).data,
            status=status.HTTP_200_OK if reused else status.HTTP_201_CREATED,
        )

    @action(methods=["GET"], detail=True)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def versions(self, request, pk=None):
        workflow = self._scoped_object(request)
        execution_counts = (
            WorkflowExecution.objects.filter(workflow_id=OuterRef("workflow_id"), workflow_version=OuterRef("version"))
            .values("workflow_id", "workflow_version")
            .annotate(total=Count("id"))
            .values("total")[:1]
        )
        records = workflow.versions.annotate(execution_count=Coalesce(Subquery(execution_counts), Value(0), output_field=IntegerField()))
        page = self.paginate_queryset(records)
        return self.get_paginated_response(WorkflowVersionSerializer(page, many=True).data)

    @action(methods=["POST"], detail=True, url_path=r"versions/(?P<version>\d+)/restore-draft")
    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def restore_version_draft(self, request, pk=None, version=None):
        scoped = self._scoped_object(request, require_operate=True)
        supplied_revision = request.data.get("draft_revision")
        username, domain = _identity(request)
        with transaction.atomic():
            workflow = Workflow.all_objects.select_for_update().get(pk=scoped.pk)
            if supplied_revision is not None and supplied_revision != workflow.draft_revision:
                return Response(
                    {"detail": "草稿已经被其他修改更新，请重新载入后再恢复", "code": "DRAFT_REVISION_CONFLICT"},
                    status=status.HTTP_409_CONFLICT,
                )
            record = get_object_or_404(workflow.versions.all(), version=version)
            workflow.definition = copy.deepcopy(record.definition)
            workflow.canvas_metadata = copy.deepcopy(record.canvas_metadata)
            workflow.has_draft = True
            workflow.draft_base_version = record.version
            workflow.draft_revision += 1
            workflow.updated_by = username
            workflow.updated_by_domain = domain
            workflow.save(
                update_fields=(
                    "definition",
                    "canvas_metadata",
                    "has_draft",
                    "draft_base_version",
                    "draft_revision",
                    "updated_by",
                    "updated_by_domain",
                    "updated_at",
                )
            )
        _audit(
            request,
            "restore_draft",
            f"将历史 v{record.version} 恢复为可编辑草稿，当前生效版本不变",
            target_type="workflow",
            target_id=workflow.id,
        )
        return Response(self.get_serializer(workflow).data)

    @action(methods=["GET"], detail=False)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def atoms(self, request):
        team = _team_id(request)
        catalog = available_atom_catalog(team)
        payload = [{key: value for key, value in item.items() if key not in {"driver", "execution_config"}} for item in catalog.values()]
        payload.sort(key=lambda item: (item["category"], item["name"], item["key"]))
        if len(payload) > 100:
            return Response({"detail": "当前组织可用原子超过 100 个上限"}, status=status.HTTP_409_CONFLICT)
        return Response(payload)

    @action(methods=["GET"], detail=False)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def targets(self, request):
        team = _team_id(request)
        source = request.query_params.get("source")
        if source not in {"node_mgmt", "job_mgmt"}:
            return Response({"detail": "source 必须是 node_mgmt 或 job_mgmt"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
        except (TypeError, ValueError):
            return Response({"detail": "分页参数非法"}, status=status.HTTP_400_BAD_REQUEST)
        query = str(request.query_params.get("query") or "").strip()[:120]
        if source == "node_mgmt":
            query_data = {
                "page": page,
                "page_size": page_size,
                "organization_ids": [team],
                "permission_data": _permission_data(request, team),
            }
            if query:
                query_data["ip" if re.fullmatch(r"[0-9a-fA-F:.]+", query) else "name"] = query
            try:
                result = NodeMgmt(is_local_client=True).node_list(query_data)
            except Exception:
                logger.warning("Target source unavailable source=node_mgmt team=%s", team)
                return Response({"detail": "节点管理目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            if not isinstance(result, dict):
                return Response({"detail": "节点管理目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
            return Response(
                {
                    "source": source,
                    "count": int(result.get("count") or 0),
                    "items": [_node_target(node) for node in result.get("nodes", [])],
                }
            )
        try:
            permission_data = _permission_data(request, team)
            job_response = (
                JobMgmt(is_local_client=True).list_automation_targets(
                    {"page": page, "page_size": page_size, "query": query},
                    {"username": permission_data["username"], "domain": permission_data["domain"], "authorized_team_ids": [team]},
                )
                or {}
            )
        except Exception:
            logger.warning("Target source unavailable source=job_mgmt team=%s", team)
            return Response({"detail": "作业平台目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not job_response.get("result"):
            return Response({"detail": "作业平台目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        data = job_response.get("data") or {}
        return Response(
            {
                "source": source,
                "count": int(data.get("count") or 0),
                "items": [_manual_target(item) for item in data.get("items", [])],
            }
        )

    @action(methods=["POST"], detail=False, url_path="targets/match")
    @HasPermission("workflow-View", app_name=APP_NAME)
    def match_targets(self, request):
        team = _team_id(request)
        source = request.data.get("source")
        raw_values = request.data.get("values")
        if isinstance(raw_values, str):
            values = [value for value in re.split(r"[\s,;]+", raw_values) if value]
        elif isinstance(raw_values, list):
            values = [str(value).strip() for value in raw_values if str(value).strip()]
        else:
            values = []
        if source not in {"node_mgmt", "job_mgmt"}:
            return Response({"detail": "source 必须是 node_mgmt 或 job_mgmt"}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= len(values) <= 100:
            return Response({"detail": "values 必须包含 1 到 100 个 IP"}, status=status.HTTP_400_BAD_REQUEST)
        unique_values = list(dict.fromkeys(values))
        try:
            if source == "node_mgmt":
                records = (
                    NodeMgmt(is_local_client=True).get_authorized_execution_targets_by_ips(
                        unique_values,
                        _permission_data(request, team),
                    )
                    or []
                )
                targets = [_node_target(node) for node in records]
            else:
                permission_data = _permission_data(request, team)
                response = (
                    JobMgmt(is_local_client=True).list_automation_targets(
                        {"ips": unique_values, "page": 1, "page_size": 100},
                        {"username": permission_data["username"], "domain": permission_data["domain"], "authorized_team_ids": [team]},
                    )
                    or {}
                )
                if not response.get("result"):
                    return Response({"detail": "作业平台目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
                targets = [_manual_target(item) for item in (response.get("data") or {}).get("items", [])]
        except Exception:
            logger.warning("Target batch match unavailable source=%s team=%s", source, team)
            return Response({"detail": f"{('节点管理' if source == 'node_mgmt' else '作业平台')}目标暂时不可用"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        by_ip = {}
        for target in targets:
            by_ip.setdefault(str(target.get("ip") or ""), []).append(target)
        seen = set()
        results = []
        for value in values:
            if value in seen:
                results.append({"value": value, "status": "duplicate", "targets": []})
                continue
            seen.add(value)
            matched = by_ip.get(value, [])
            match_status = "matched" if len(matched) == 1 else "ambiguous" if len(matched) > 1 else "not_found"
            results.append({"value": value, "status": match_status, "targets": matched})
        return Response({"source": source, "results": results})

    @action(methods=["GET"], detail=False)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def health(self, request):
        return Response(ConductorClient().health())


class AtomConfigTemplateViewSet(AuthViewSet):
    """当前组织共享的原子配置模板。"""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = AtomConfigTemplate.objects.all()
    serializer_class = AtomConfigTemplateSerializer
    pagination_class = WorkflowPageNumberPagination
    ORGANIZATION_FIELD = "organization_id"

    def _scoped_queryset(self, request):
        team = self._validate_current_team_permission(request)
        return self.get_queryset().filter(organization_id=team), team

    def _scoped_object(self, request):
        queryset, _ = self._scoped_queryset(request)
        return get_object_or_404(queryset, pk=self.kwargs.get("pk"))

    @staticmethod
    def _serializer_context(request, *, team):
        return {"request": request, "team": team}

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        queryset, _ = self._scoped_queryset(request)
        atom_key = str(request.query_params.get("atom_key") or "").strip()
        if not atom_key:
            return Response({"detail": "atom_key 必填"}, status=status.HTTP_400_BAD_REQUEST)
        queryset = queryset.filter(atom_key=atom_key)
        query = str(request.query_params.get("query") or "").strip()
        if query:
            queryset = queryset.filter(name__icontains=query[:120])
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self._scoped_object(request)).data)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def create(self, request, *args, **kwargs):
        team = self._validate_current_team_permission(request)
        serializer = self.get_serializer(
            data=request.data,
            context=self._serializer_context(request, team=team),
        )
        serializer.is_valid(raise_exception=True)
        username, domain = _identity(request)
        try:
            template = serializer.save(
                organization_id=team,
                created_by=username,
                updated_by=username,
                domain=domain,
                updated_by_domain=domain,
            )
        except IntegrityError:
            return Response({"name": ["当前原子下已存在同名配置模板"]}, status=status.HTTP_400_BAD_REQUEST)
        _audit(request, "create", "创建原子配置模板", target_type="atom_config_template", target_id=template.pk)
        return Response(self.get_serializer(template).data, status=status.HTTP_201_CREATED)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def partial_update(self, request, *args, **kwargs):
        template = self._scoped_object(request)
        team = self._validate_current_team_permission(request)
        serializer = self.get_serializer(
            template,
            data=request.data,
            partial=True,
            context=self._serializer_context(request, team=team),
        )
        serializer.is_valid(raise_exception=True)
        username, domain = _identity(request)
        try:
            template = serializer.save(updated_by=username, updated_by_domain=domain)
        except IntegrityError:
            return Response({"name": ["当前原子下已存在同名配置模板"]}, status=status.HTTP_400_BAD_REQUEST)
        _audit(request, "manage", "更新原子配置模板", target_type="atom_config_template", target_id=template.pk)
        return Response(self.get_serializer(template).data)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def destroy(self, request, *args, **kwargs):
        template = self._scoped_object(request)
        template_id = template.pk
        template.delete()
        _audit(request, "delete", "删除原子配置模板", target_type="atom_config_template", target_id=template_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AtomDefinitionViewSet(AuthViewSet):
    http_method_names = ["get", "post", "head", "options"]
    lookup_value_regex = r"[^/]+"
    queryset = AtomDefinition.objects.filter(source_type=AtomDefinition.SourceType.PACKAGE)
    serializer_class = AtomDefinitionSerializer
    pagination_class = WorkflowPageNumberPagination
    ORGANIZATION_FIELD = "team"

    def _scoped_queryset(self, request):
        team = self._validate_current_team_permission(request)
        queryset = self.get_queryset().filter(Q(team=[]) | build_json_membership_query(self.get_queryset(), "team", [team]))
        return queryset, team

    def _scoped_object(self, request):
        queryset, _ = self._scoped_queryset(request)
        return get_object_or_404(queryset, pk=self.kwargs.get("pk"))

    @staticmethod
    def _builtin_items(
        query: str,
        category: str,
        node_type: str,
        *,
        include_detail: bool = False,
    ):
        raw_items = [
            *({**item, "node_type": "ACTION"} for item in atom_catalog_payload() if item.get("catalog_visible", True)),
            *system_node_catalog_payload(),
        ]
        stored = {atom.key: atom for atom in AtomDefinition.objects.filter(key__in=[item["key"] for item in raw_items])}
        items = []
        for item in raw_items:
            record = stored.get(item["key"])
            if query and query.casefold() not in f"{item['name']} {item['key']}".casefold():
                continue
            if category and category not in {item["category"], item["node_type"]}:
                continue
            if node_type and item["node_type"] != node_type:
                continue
            payload = {
                "key": item["key"],
                "name": item["name"],
                "category": item["category"],
                "node_type": item["node_type"],
                "description": item["description"],
                "source_type": item["source_type"],
                "created_by": record.created_by if record is not None else "system",
                "updated_by": record.updated_by if record is not None else "system",
                "created_at": record.created_at if record is not None else None,
                "updated_at": record.updated_at if record is not None else None,
            }
            if include_detail:
                payload.update(
                    {
                        "input_schema": item.get("input_schema") or {},
                        "output_schema": item.get("output_schema") or {},
                        "ui_schema": item.get("ui_schema") or {},
                    }
                )
            items.append(payload)
        return items

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        queryset, _team = self._scoped_queryset(request)
        query = str(request.query_params.get("query") or "").strip()
        category = str(request.query_params.get("category") or "").strip()
        node_type = str(request.query_params.get("node_type") or "").strip().upper()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(key__icontains=query))
        if category:
            queryset = queryset.filter(category=category)
        if node_type and node_type not in {"TRIGGER", "ACTION", "CONTROL", "RETURN"}:
            return Response({"detail": "node_type 非法"}, status=status.HTTP_400_BAD_REQUEST)
        if node_type and node_type != "ACTION":
            queryset = queryset.none()
        builtins = self._builtin_items(query, category, node_type)
        try:
            page_number = int(request.query_params.get("page") or 1)
            page_size = int(request.query_params.get("page_size") or self.pagination_class.page_size)
        except (TypeError, ValueError):
            return Response({"detail": "page 或 page_size 非法"}, status=status.HTTP_400_BAD_REQUEST)
        if page_number < 1 or not 1 <= page_size <= self.pagination_class.max_page_size:
            return Response({"detail": "page 或 page_size 超出范围"}, status=status.HTTP_400_BAD_REQUEST)
        package_count = queryset.count()
        total = len(builtins) + package_count
        start = (page_number - 1) * page_size
        end = start + page_size
        items = builtins[start:end]
        if len(items) < page_size and end > len(builtins):
            package_start = max(0, start - len(builtins))
            package_end = package_start + page_size - len(items)
            items.extend(AtomDefinitionSummarySerializer(queryset[package_start:package_end], many=True).data)
        return Response({"count": total, "items": items})

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        self._validate_current_team_permission(request)
        builtin = next(
            (item for item in self._builtin_items("", "", "", include_detail=True) if item["key"] == self.kwargs.get("pk")),
            None,
        )
        if builtin is not None:
            return Response(builtin)
        return Response(self.get_serializer(self._scoped_object(request)).data)

    @HasPermission("workflow-Manage", app_name=APP_NAME)
    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "MVP 原子由研发注册包同步，页面不支持在线创建"},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class WorkflowExecutionViewSet(AuthViewSet):
    http_method_names = ["get", "post", "head", "options"]
    queryset = WorkflowExecution.objects.select_related("workflow").prefetch_related(
        "atom_executions",
        "interactions",
        "artifacts__atom_execution",
    )
    serializer_class = WorkflowExecutionSerializer
    ORGANIZATION_FIELD = "team"
    pagination_class = WorkflowPageNumberPagination

    def _scoped_queryset(self, request, *, require_operate=False):
        team = self._validate_current_team_permission(request)
        workflows = filter_workflow_queryset(
            request,
            Workflow.all_objects.all(),
            team,
            require_operate=require_operate,
        )
        return self.get_queryset().filter(workflow_id__in=workflows.values("pk"))

    def _scoped_object(self, request, *, require_operate=False):
        return get_object_or_404(
            self._scoped_queryset(request, require_operate=require_operate),
            pk=self.kwargs.get("pk"),
        )

    def create(self, request, *args, **kwargs):
        return Response({"detail": "执行记录只能由流程或触发器创建"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        username, _ = _identity(request)
        actionable = WorkflowInteraction.objects.filter(
            status=WorkflowInteraction.Status.PENDING,
            interaction_type=WorkflowInteraction.Type.APPROVAL,
        ).filter(build_json_membership_query(WorkflowInteraction.objects.all(), "candidate_users", [username]))
        pending = WorkflowInteraction.objects.filter(status=WorkflowInteraction.Status.PENDING).only("execution_id", "title", "task_reference")
        queryset = (
            self.filter_queryset(self._scoped_queryset(request))
            .annotate(
                artifact_count=Count("artifacts", distinct=True),
                pending_approval_count=Count(
                    "interactions",
                    filter=Q(
                        interactions__status=WorkflowInteraction.Status.PENDING,
                        interactions__interaction_type=WorkflowInteraction.Type.APPROVAL,
                    ),
                    distinct=True,
                ),
            )
            .prefetch_related(
                Prefetch("interactions", queryset=actionable, to_attr="actionable_approvals"),
                Prefetch("interactions", queryset=pending, to_attr="pending_interactions"),
            )
        )
        if request.query_params.get("workflow_id"):
            queryset = queryset.filter(workflow_id=request.query_params["workflow_id"])
        if request.query_params.get("query"):
            queryset = queryset.filter(workflow__name__icontains=str(request.query_params["query"]).strip()[:120])
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("trigger_type"):
            queryset = queryset.filter(trigger_type=request.query_params["trigger_type"])
        mode = str(request.query_params.get("mode") or "").upper()
        if mode:
            if mode not in WorkflowExecution.Mode.values:
                return Response({"detail": "mode 非法"}, status=status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(mode=mode)
        if request.query_params.get("mine") == "1":
            queryset = queryset.filter(pk__in=Subquery(actionable.values("execution_id")))
        queryset = queryset.order_by("-created_at", "-id")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(WorkflowExecutionListSerializer(page, many=True, context={"request": request}).data)

    @action(methods=["GET"], detail=False)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def dashboard(self, request):
        team = self._validate_current_team_permission(request)
        username, _ = _identity(request)
        current_timezone = timezone.get_current_timezone()
        today = timezone.localdate()
        today_start = timezone.make_aware(datetime.combine(today, time.min), current_timezone)
        seven_day_start_date = today - timedelta(days=6)
        seven_day_start = timezone.make_aware(datetime.combine(seven_day_start_date, time.min), current_timezone)

        workflow_queryset = filter_workflow_queryset(request, Workflow.objects.all(), team)
        execution_queryset = self.get_queryset().filter(
            workflow_id__in=workflow_queryset.values("pk"),
            mode=WorkflowExecution.Mode.PRODUCTION,
        )
        today_queryset = execution_queryset.filter(created_at__gte=today_start)
        seven_day_queryset = execution_queryset.filter(created_at__gte=seven_day_start)

        success_statuses = {
            WorkflowExecution.Status.SUCCEEDED,
        }
        outcome_statuses = success_statuses | {
            WorkflowExecution.Status.FAILED,
            WorkflowExecution.Status.TIMED_OUT,
        }
        outcome_counts = dict(seven_day_queryset.filter(status__in=outcome_statuses).values_list("status").annotate(count=Count("id")))
        successful = sum(outcome_counts.get(item, 0) for item in success_statuses)
        outcome_total = sum(outcome_counts.values())

        status_counts = dict(seven_day_queryset.values_list("status").annotate(count=Count("id")))
        status_distribution = [
            {
                "status": execution_status,
                "label": workflow_message(
                    request,
                    f"choice.execution_status.{execution_status}",
                    str(default_label),
                ),
                "count": status_counts.get(execution_status, 0),
            }
            for execution_status, default_label in WorkflowExecution.Status.choices
        ]

        trend_rows = (
            seven_day_queryset.annotate(day=TruncDate("created_at", tzinfo=current_timezone)).values("day", "status").annotate(count=Count("id"))
        )
        trend_by_day = {seven_day_start_date + timedelta(days=offset): {} for offset in range(7)}
        for row in trend_rows:
            trend_by_day.setdefault(row["day"], {})[row["status"]] = row["count"]
        trend = []
        for day, day_counts in trend_by_day.items():
            total = sum(day_counts.values())
            known_total = sum(
                day_counts.get(execution_status, 0)
                for execution_status in (
                    WorkflowExecution.Status.SUCCEEDED,
                    WorkflowExecution.Status.FAILED,
                    WorkflowExecution.Status.TIMED_OUT,
                )
            )
            trend.append(
                {
                    "date": day.isoformat(),
                    "total": total,
                    "succeeded": day_counts.get(WorkflowExecution.Status.SUCCEEDED, 0),
                    "failed": day_counts.get(WorkflowExecution.Status.FAILED, 0),
                    "timed_out": day_counts.get(WorkflowExecution.Status.TIMED_OUT, 0),
                    "other": total - known_total,
                }
            )

        pending_approval_queryset = (
            WorkflowInteraction.objects.filter(
                status=WorkflowInteraction.Status.PENDING,
                interaction_type=WorkflowInteraction.Type.APPROVAL,
            )
            .filter(build_json_membership_query(WorkflowInteraction.objects.all(), "team", [team]))
            .filter(build_json_membership_query(WorkflowInteraction.objects.all(), "candidate_users", [username]))
            .filter(execution__workflow_id__in=workflow_queryset.values("pk"))
            .select_related("execution__workflow")
            .order_by("created_at", "id")
        )
        pending_approvals = pending_approval_queryset.count()

        recent_executions = execution_queryset.order_by("-created_at", "-id")[:10]

        return Response(
            {
                "kpis": {
                    "workflow_total": workflow_queryset.count(),
                    "published_workflows": workflow_queryset.filter(current_version__gt=0).count(),
                    "enabled_workflows": workflow_queryset.filter(current_version__gt=0, enabled=True).count(),
                    "draft_workflows": workflow_queryset.filter(Q(current_version=0) | Q(has_draft=True)).count(),
                    "today_executions": today_queryset.count(),
                    "success_rate": round(successful * 100 / outcome_total, 1) if outcome_total else None,
                    "running_executions": execution_queryset.filter(status=WorkflowExecution.Status.RUNNING).count(),
                    "queued_executions": execution_queryset.filter(status=WorkflowExecution.Status.QUEUED).count(),
                    "failed_executions": outcome_counts.get(WorkflowExecution.Status.FAILED, 0)
                    + outcome_counts.get(WorkflowExecution.Status.TIMED_OUT, 0),
                    "pending_approvals": pending_approvals,
                },
                "trend": trend,
                "status_distribution": status_distribution,
                "recent_executions": WorkflowExecutionListSerializer(
                    recent_executions,
                    many=True,
                    context={"request": request},
                ).data,
                "pending_approvals": WorkflowDashboardApprovalSerializer(pending_approval_queryset[:3], many=True).data,
            }
        )

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        execution = self._scoped_object(request)
        if execution.conductor_workflow_id and execution.status in {
            WorkflowExecution.Status.QUEUED,
            WorkflowExecution.Status.RUNNING,
            WorkflowExecution.Status.WAITING_APPROVAL,
            WorkflowExecution.Status.TERMINATING,
        }:
            try:
                apply_remote_execution(execution, ConductorClient().get_execution(execution.conductor_workflow_id))
            except ConductorUnavailable:
                logger.warning("Conductor sync unavailable execution_id=%s", execution.id)
        return Response(self.get_serializer(execution).data)

    @action(methods=["GET"], detail=True)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def nodes(self, request, pk=None):
        execution = self._scoped_object(request)
        username, _ = _identity(request)
        return Response(build_execution_node_summary(execution, username=username))

    @action(methods=["GET"], detail=True, url_path=r"nodes/(?P<node_reference>[^/.]+)")
    @HasPermission("workflow-View", app_name=APP_NAME)
    def node_detail(self, request, pk=None, node_reference=None):
        execution = self._scoped_object(request)
        username, _ = _identity(request)
        detail = build_execution_node_detail(
            execution,
            node_reference=str(node_reference or ""),
            username=username,
            instance_id=request.query_params.get("instance_id"),
            include_technical=bool(getattr(request.user, "is_superuser", False)),
        )
        if detail is None:
            return Response({"detail": "执行节点不存在"}, status=status.HTTP_404_NOT_FOUND)
        return Response(detail)

    def _control(self, request, *, action_name: str, source_statuses: set[str], target_status: str):
        execution = self._scoped_object(request, require_operate=True)
        if execution.status not in source_statuses:
            return Response({"detail": "当前执行状态不支持该操作"}, status=status.HTTP_409_CONFLICT)
        if not execution.conductor_workflow_id:
            return Response({"detail": "执行记录缺少 Conductor Workflow ID"}, status=status.HTTP_409_CONFLICT)
        conductor = ConductorClient()
        try:
            getattr(conductor, action_name)(execution.conductor_workflow_id)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        execution.status = target_status
        execution.save(update_fields=("status", "updated_at"))
        _audit(request, action_name, f"执行控制: {action_name}", target_type="execution", target_id=execution.id)
        return Response(self.get_serializer(execution).data)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def terminate(self, request, pk=None):
        execution = self._scoped_object(request, require_operate=True)
        if execution.status not in {
            WorkflowExecution.Status.QUEUED,
            WorkflowExecution.Status.RUNNING,
            WorkflowExecution.Status.WAITING_APPROVAL,
        }:
            return Response({"detail": "当前执行已是终态"}, status=status.HTTP_409_CONFLICT)
        if not execution.conductor_workflow_id:
            return Response({"detail": "执行记录缺少 Conductor Workflow ID"}, status=status.HTTP_409_CONFLICT)
        reason = str(request.data.get("reason") or "").strip()[:500]
        if not reason:
            return Response({"detail": "终止原因必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ConductorClient().terminate_workflow(execution.conductor_workflow_id, reason=reason)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        execution.status = WorkflowExecution.Status.TERMINATING
        execution.termination_reason = reason
        execution.interactions.filter(status=WorkflowInteraction.Status.PENDING).update(
            status=WorkflowInteraction.Status.CANCELLED,
            handled_at=timezone.now(),
        )
        execution.save(update_fields=("status", "termination_reason", "updated_at"))
        _audit(request, "terminate", "终止流程执行", target_type="execution", target_id=execution.id)
        return Response(self.get_serializer(execution).data)

    @staticmethod
    def _rerunnable(execution):
        return (
            execution.status
            in {
                WorkflowExecution.Status.SUCCEEDED,
                WorkflowExecution.Status.FAILED,
                WorkflowExecution.Status.TIMED_OUT,
                WorkflowExecution.Status.TERMINATED,
            }
            and execution.workflow_version > 0
            and execution.mode == WorkflowExecution.Mode.PRODUCTION
            and execution.workflow.enabled
        )

    @action(methods=["GET"], detail=True, url_path="launch-plan")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def launch_plan(self, request, pk=None):
        original = self._scoped_object(request, require_operate=True)
        if not self._rerunnable(original):
            return Response({"detail": "只能重新执行已结束的正式版本"}, status=status.HTTP_409_CONFLICT)
        version = WorkflowVersion.objects.filter(
            workflow=original.workflow,
            version=original.workflow_version,
        ).first()
        if version is None:
            return Response({"detail": "原执行对应的流程版本不存在"}, status=status.HTTP_409_CONFLICT)
        username, domain = _identity(request)
        try:
            target_fields = extract_target_fields(version.canvas_metadata)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(
            build_launch_plan(
                workflow_id=original.workflow_id,
                workflow_name=original.workflow.name,
                workflow_version=version.version,
                canvas_metadata=version.canvas_metadata,
                team=_team_id(request),
                username=username,
                domain=domain,
                target_fields=target_fields,
                parent_execution_id=str(original.id),
            )
        )

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def rerun(self, request, pk=None):
        original = self._scoped_object(request, require_operate=True)
        if not self._rerunnable(original):
            return Response({"detail": "只能重新执行已结束的正式版本"}, status=status.HTTP_409_CONFLICT)
        team = _team_id(request)
        username, domain = _identity(request)
        launch_token = request.data.get("launch_token")
        try:
            launch_context = verify_launch_token(
                launch_token,
                workflow_id=original.workflow_id,
                team=team,
                username=username,
                domain=domain,
            )
        except LaunchPlanTokenError as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        if launch_context.get("parent_execution_id") != str(original.id):
            return Response({"detail": "启动凭证与原执行不匹配"}, status=status.HTTP_409_CONFLICT)
        if launch_context["workflow_version"] != original.workflow_version:
            return Response({"detail": "启动凭证与原执行版本不匹配"}, status=status.HTTP_409_CONFLICT)
        version = WorkflowVersion.objects.filter(
            workflow=original.workflow,
            version=original.workflow_version,
        ).first()
        if version is None:
            return Response({"detail": "原执行对应的流程版本不存在"}, status=status.HTTP_409_CONFLICT)
        try:
            inputs = validate_workflow_inputs(
                copy.deepcopy(request.data.get("inputs") or {}),
                version.canvas_metadata.get("input_schema") or {},
            )
            target_fields = extract_target_fields(version.canvas_metadata)
            target_snapshot = {}
            if target_fields:
                resolution = resolve_target_fields(
                    inputs,
                    target_fields,
                    gateway=RpcTargetGateway(
                        team=team,
                        permission_data=_permission_data(request, team),
                        node_client=NodeMgmt(is_local_client=True),
                        job_client=JobMgmt(is_local_client=True),
                    ),
                )
                if resolution.offline_targets and request.data.get("offline_confirmed") is not True:
                    return Response(
                        {
                            "detail": f"{len(resolution.offline_targets)} 台主机当前离线，需要二次确认",
                            "code": "OFFLINE_CONFIRMATION_REQUIRED",
                            "offline_targets": resolution.offline_targets,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                inputs = resolution.inputs
                target_snapshot = resolution.snapshot
                target_snapshot["offline_confirmed"] = bool(resolution.offline_targets)
            execution = start_execution(
                original.workflow,
                inputs=inputs,
                started_by=username,
                domain=domain,
                client=ConductorClient(),
                version_number=original.workflow_version,
                parent_execution=original,
                launch_token_hash=launch_token_digest(launch_token),
                target_snapshot=target_snapshot,
            )
        except TargetResolutionError as error:
            response_status = status.HTTP_403_FORBIDDEN if "不存在或无权访问" in str(error) else status.HTTP_400_BAD_REQUEST
            return Response({"detail": str(error)}, status=response_status)
        except (ValueError, WorkflowVersion.DoesNotExist) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TargetDependencyUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        reused = bool(getattr(execution, "_launch_reused", False))
        if not reused:
            _audit(request, "rerun", "重新执行冻结流程版本", target_type="execution", target_id=execution.id)
        return Response(
            self.get_serializer(execution).data,
            status=status.HTTP_200_OK if reused else status.HTTP_201_CREATED,
        )


class WorkflowInteractionViewSet(AuthViewSet):
    http_method_names = ["get", "post", "head", "options"]
    queryset = WorkflowInteraction.objects.select_related("execution", "execution__workflow")
    serializer_class = WorkflowInteractionSerializer
    ORGANIZATION_FIELD = "team"
    pagination_class = WorkflowPageNumberPagination

    def _scoped_queryset(self, request, *, require_operate=False):
        team = self._validate_current_team_permission(request)
        workflows = filter_workflow_queryset(
            request,
            Workflow.all_objects.all(),
            team,
            require_operate=require_operate,
        )
        return self.get_queryset().filter(execution__workflow_id__in=workflows.values("pk"))

    def _scoped_object(self, request, *, require_operate=False):
        return get_object_or_404(
            self._scoped_queryset(request, require_operate=require_operate),
            pk=self.kwargs.get("pk"),
        )

    def create(self, request, *args, **kwargs):
        return Response({"detail": "人工处理项只能由执行引擎产生"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        username, _ = _identity(request)
        queryset = self._scoped_queryset(request)
        if request.query_params.get("execution_id"):
            queryset = queryset.filter(execution_id=request.query_params["execution_id"])
        if request.query_params.get("mine") == "1":
            queryset = queryset.filter(
                build_json_membership_query(queryset, "candidate_users", [username]),
                status=WorkflowInteraction.Status.PENDING,
            )
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self._scoped_object(request)).data)

    @action(methods=["GET"], detail=False, url_path="pending-count")
    @HasPermission("workflow-View", app_name=APP_NAME)
    def pending_count(self, request):
        username, _ = _identity(request)
        queryset = self._scoped_queryset(request).filter(
            build_json_membership_query(self.get_queryset(), "candidate_users", [username]),
            interaction_type=WorkflowInteraction.Type.APPROVAL,
            status=WorkflowInteraction.Status.PENDING,
        )
        return Response({"count": queryset.count()})

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Approve", app_name=APP_NAME)
    def decide(self, request, pk=None):
        interaction = self._scoped_object(request)
        username, domain = _identity(request)
        try:
            decided = decide_interaction(
                interaction.id,
                username=username,
                domain=domain,
                decision=request.data.get("decision"),
                comment=request.data.get("comment", ""),
                client=ConductorClient(),
            )
        except InteractionForbidden as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        except InteractionConflict as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        _audit(request, "approve", f"处理审批: {decided.status}", target_type="workflow_interaction", target_id=decided.id)
        return Response(self.get_serializer(decided).data)


class WorkflowTriggerViewSet(AuthViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    queryset = WorkflowTrigger.objects.select_related("workflow").filter(workflow__deleted_at__isnull=True)
    serializer_class = WorkflowTriggerSerializer
    ORGANIZATION_FIELD = "team"
    pagination_class = WorkflowPageNumberPagination

    def _scoped_queryset(self, request, *, require_operate=False):
        team = self._validate_current_team_permission(request)
        workflows = filter_workflow_queryset(
            request,
            Workflow.objects.all(),
            team,
            require_operate=require_operate,
        )
        return self.get_queryset().filter(workflow_id__in=workflows.values("pk"))

    def _scoped_object(self, request, *, require_operate=False):
        return get_object_or_404(
            self._scoped_queryset(request, require_operate=require_operate),
            pk=self.kwargs.get("pk"),
        )

    def _scoped_workflow(self, request, workflow_id):
        team = self._validate_current_team_permission(request)
        workflows = filter_workflow_queryset(
            request,
            Workflow.objects.all(),
            team,
            require_operate=True,
        )
        return team, get_object_or_404(workflows, pk=workflow_id)

    @staticmethod
    def _nats_draft_node(workflow, node_key):
        nodes = workflow.canvas_metadata.get("trigger_nodes") or []
        return next(
            (
                node
                for node in nodes
                if isinstance(node, dict) and node.get("id") == node_key and node.get("trigger_type") == WorkflowTrigger.Type.NATS
            ),
            None,
        )

    @staticmethod
    def _webhook_draft_node(workflow, node_key):
        nodes = workflow.canvas_metadata.get("trigger_nodes") or []
        return next(
            (
                node
                for node in nodes
                if isinstance(node, dict) and node.get("id") == node_key and node.get("trigger_type") == WorkflowTrigger.Type.WEBHOOK
            ),
            None,
        )

    @HasPermission("workflow-View", app_name=APP_NAME)
    def list(self, request, *args, **kwargs):
        queryset = self._scoped_queryset(request)
        if request.query_params.get("workflow_id"):
            queryset = queryset.filter(workflow_id=request.query_params["workflow_id"])
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @HasPermission("workflow-View", app_name=APP_NAME)
    def retrieve(self, request, *args, **kwargs):
        return Response(self.get_serializer(self._scoped_object(request)).data)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def create(self, request, *args, **kwargs):
        return Response({"detail": "触发器必须在流程画布中创建并随版本发布"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def partial_update(self, request, *args, **kwargs):
        return Response({"detail": "触发器必须在流程画布中编辑"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @HasPermission("workflow-Edit", app_name=APP_NAME)
    def destroy(self, request, *args, **kwargs):
        return Response({"detail": "触发器必须在流程画布中删除"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(methods=["POST"], detail=False, url_path="schedule-preview")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def schedule_preview(self, request):
        request_serializer = SchedulePreviewRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            payload = build_schedule_preview(
                request_serializer.validated_data["config"],
                timezone_name=resolve_user_timezone(request.user),
                count=request_serializer.validated_data["count"],
            )
        except DefinitionValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @action(methods=["POST"], detail=False, url_path="nats-test-session")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def nats_test_session(self, request):
        request_serializer = NatsTestSessionRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        team, workflow = self._scoped_workflow(request, request_serializer.validated_data["workflow_id"])
        node_key = request_serializer.validated_data["node_key"]
        if self._nats_draft_node(workflow, node_key) is None:
            return Response({"detail": "NATS 触发节点不存在"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(create_nats_test_session(team_id=int(team), workflow_id=workflow.pk, node_key=node_key))

    @action(methods=["POST"], detail=False, url_path="nats-test-listen")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def nats_test_listen(self, request):
        request_serializer = NatsTestListenRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            session = read_nats_test_session(request_serializer.validated_data["token"])
        except NatsTestSessionError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        team, workflow = self._scoped_workflow(request, session["workflow_id"])
        if int(team) != int(session["team_id"]):
            return Response({"detail": "NATS 测试会话不属于当前组织"}, status=status.HTTP_403_FORBIDDEN)
        if self._nats_draft_node(workflow, session["node_key"]) is None:
            return Response({"detail": "NATS 触发节点不存在"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = wait_for_nats_test_event(session["subject"])
        except NatsTestTimeout as error:
            return Response({"detail": str(error)}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except NatsTestSessionError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    @action(methods=["POST"], detail=False, url_path="webhook-test-session")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def webhook_test_session(self, request):
        request_serializer = WebhookTestSessionRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        team, workflow = self._scoped_workflow(request, request_serializer.validated_data["workflow_id"])
        node_key = request_serializer.validated_data["node_key"]
        if self._webhook_draft_node(workflow, node_key) is None:
            return Response({"detail": "Webhook 触发节点不存在"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(create_webhook_test_session(team_id=int(team), workflow_id=workflow.pk, node_key=node_key))

    @action(methods=["POST"], detail=False, url_path="webhook-test-listen")
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def webhook_test_listen(self, request):
        request_serializer = WebhookTestListenRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            session = read_webhook_test_session(request_serializer.validated_data["token"])
        except WebhookTestSessionError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        team, workflow = self._scoped_workflow(request, session["workflow_id"])
        if int(team) != int(session["team_id"]):
            return Response({"detail": "Webhook 测试会话不属于当前组织"}, status=status.HTTP_403_FORBIDDEN)
        if self._webhook_draft_node(workflow, session["node_key"]) is None:
            return Response({"detail": "Webhook 触发节点不存在"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = wait_for_webhook_test_event(request_serializer.validated_data["token"])
        except WebhookTestTimeout as error:
            return Response({"detail": str(error)}, status=status.HTTP_408_REQUEST_TIMEOUT)
        except WebhookTestSessionError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    @action(methods=["POST"], detail=True)
    @HasPermission("workflow-Execute", app_name=APP_NAME)
    def invoke(self, request, pk=None):
        trigger = self._scoped_object(request, require_operate=True)
        username, domain = _identity(request)
        try:
            execution, created = invoke_trigger(
                trigger,
                inputs=request.data.get("inputs") or {},
                idempotency_key=request.data.get("idempotency_key") or "",
                started_by=username,
                domain=domain,
            )
        except DefinitionValidationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        except TriggerConflict as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        except ConductorUnavailable as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        _audit(request, "execute", "手动调用流程触发器", target_type="execution", target_id=execution.id)
        return Response(
            WorkflowExecutionSerializer(execution, context={"request": request}).data,
            status=response_status,
        )


class ExecutionArtifactViewSet(AuthViewSet):
    queryset = ExecutionArtifact.objects.select_related("execution", "execution__workflow")
    ORGANIZATION_FIELD = "team"

    @action(methods=["GET"], detail=False, url_path="shared", permission_classes=[AllowAny], authentication_classes=[])
    def shared(self, request):
        try:
            payload = read_report_download_link(str(request.query_params.get("token") or ""))
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_403_FORBIDDEN)
        artifact = ExecutionArtifact.objects.filter(pk=payload["artifact_id"]).first()
        if artifact is None or artifact.team != [payload["team"]] or str(artifact.execution_id) != str(payload["execution_id"]):
            return Response({"detail": workflow_message(request, "message.report_link_invalid", "报告下载链接无效")}, status=status.HTTP_403_FORBIDDEN)
        if artifact.deleted_at or artifact.expires_at <= timezone.now():
            return Response({"detail": workflow_message(request, "message.report_expired", "报告已过期")}, status=status.HTTP_410_GONE)
        if artifact.size > MAX_ARTIFACT_DOWNLOAD_BYTES:
            return Response(
                {"detail": workflow_message(request, "message.report_too_large", "报告文件超过下载大小限制")}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        try:
            content, _, _ = WorkflowObjectStore().get(artifact.object_key)
        except ArtifactTooLarge:
            return Response(
                {"detail": workflow_message(request, "message.report_too_large", "报告文件超过下载大小限制")}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        except Exception:
            return Response(
                {"detail": workflow_message(request, "message.report_unavailable", "报告文件暂不可用")}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        response = FileResponse(BytesIO(content), content_type=artifact.content_type, as_attachment=True, filename=artifact.filename)
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @action(methods=["GET"], detail=True)
    @HasPermission("workflow-View", app_name=APP_NAME)
    def download(self, request, pk=None):
        team = self._validate_current_team_permission(request)
        workflows = filter_workflow_queryset(request, Workflow.all_objects.all(), team)
        artifact = get_object_or_404(
            self.get_queryset().filter(execution__workflow_id__in=workflows.values("pk")),
            pk=pk,
        )
        if artifact.deleted_at or artifact.expires_at <= timezone.now():
            return Response({"detail": workflow_message(request, "message.report_expired", "报告已过期")}, status=status.HTTP_410_GONE)
        if artifact.size > MAX_ARTIFACT_DOWNLOAD_BYTES:
            return Response(
                {"detail": workflow_message(request, "message.report_too_large", "报告文件超过下载大小限制")}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        try:
            content, _, _ = WorkflowObjectStore().get(artifact.object_key)
        except ArtifactTooLarge:
            return Response(
                {"detail": workflow_message(request, "message.report_too_large", "报告文件超过下载大小限制")}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            )
        except Exception:
            return Response(
                {"detail": workflow_message(request, "message.report_unavailable", "报告文件暂不可用")}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        response = FileResponse(BytesIO(content), content_type=artifact.content_type, as_attachment=True, filename=artifact.filename)
        response["X-Content-Type-Options"] = "nosniff"
        _audit(request, "download", "下载巡检报告", target_type="execution_artifact", target_id=artifact.id)
        return response

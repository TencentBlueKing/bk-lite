from __future__ import annotations

import copy
import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.workflow_orchestration.models import Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow_orchestration.services.atom_registry import available_atom_catalog, ensure_platform_atom, task_definition_from_catalog_item
from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS
from apps.workflow_orchestration.services.capability_profiles import capability_resource_snapshot
from apps.workflow_orchestration.services.conductor import ConductorClient, ConductorUnavailable
from apps.workflow_orchestration.services.data_contracts import redact_sensitive_inputs, seal_sensitive_inputs
from apps.workflow_orchestration.services.definitions import prepare_definition_for_publish


def _system_context(
    workflow: Workflow,
    *,
    execution_id: str,
    version: int,
    trigger_type: str,
    trigger_id: str,
    started_by: str,
) -> dict[str, Any]:
    team = str(workflow.team[0]) if workflow.team else ""
    return {
        "execution_id": execution_id,
        "workflow_id": str(workflow.pk),
        "workflow_version": version,
        "organization_id": team,
        "trigger_id": trigger_id,
        "trigger_type": trigger_type,
        "actor_id": started_by,
        "actor_name": started_by,
        "started_at": timezone.now().isoformat(),
        "trace_id": execution_id,
    }


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


@transaction.atomic
def _claim_execution(
    workflow: Workflow,
    *,
    inputs: dict[str, Any],
    started_by: str,
    domain: str,
    version_number: int | None = None,
    mode: str = WorkflowExecution.Mode.PRODUCTION,
    trigger_type: str = "FORM",
    trigger_id: str = "",
    parent_execution: WorkflowExecution | None = None,
    launch_token_hash: str | None = None,
    target_snapshot: dict[str, Any] | None = None,
) -> tuple[WorkflowExecution, WorkflowVersion, bool]:
    workflow = Workflow.all_objects.select_for_update().get(pk=workflow.pk)
    if workflow.deleted_at is not None:
        raise ValueError("流程已删除，不能创建新执行")
    if workflow.status != Workflow.Status.PUBLISHED:
        raise ValueError("只能执行已发布流程")
    if mode == WorkflowExecution.Mode.PRODUCTION and not workflow.enabled:
        raise ValueError("流程已停用")
    selected_version = version_number or workflow.current_version
    if not selected_version:
        raise ValueError("请先发布流程")
    version = WorkflowVersion.objects.get(workflow=workflow, version=selected_version)
    defaults = {
        "workflow": workflow,
        "workflow_version": version.version,
        "team": workflow.team,
        "input": copy.deepcopy(inputs),
        "started_by": started_by,
        "domain": domain,
        "definition_snapshot": copy.deepcopy(version.definition),
        "resource_snapshot": copy.deepcopy(version.resource_snapshot),
        "target_snapshot": copy.deepcopy(target_snapshot or {}),
        "mode": mode,
        "trigger_type": trigger_type,
        "trigger_id": trigger_id,
        "parent_execution": parent_execution,
    }
    if launch_token_hash:
        execution, created = WorkflowExecution.objects.get_or_create(
            launch_token_hash=launch_token_hash,
            defaults=defaults,
        )
        if not created:
            return execution, version, False
    else:
        execution = WorkflowExecution.objects.create(**defaults)
    return execution, version, True


def start_execution(
    workflow: Workflow,
    *,
    inputs: dict[str, Any],
    started_by: str,
    domain: str,
    client: ConductorClient | None = None,
    version_number: int | None = None,
    mode: str = WorkflowExecution.Mode.PRODUCTION,
    trigger_type: str = "FORM",
    trigger_id: str = "",
    parent_execution: WorkflowExecution | None = None,
    launch_token_hash: str | None = None,
    target_snapshot: dict[str, Any] | None = None,
) -> WorkflowExecution:
    execution, version, created = _claim_execution(
        workflow,
        inputs=inputs,
        started_by=started_by,
        domain=domain,
        version_number=version_number,
        mode=mode,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
        parent_execution=parent_execution,
        launch_token_hash=launch_token_hash,
        target_snapshot=target_snapshot,
    )
    execution._launch_reused = not created
    if not created:
        return execution
    conductor_inputs = {
        **seal_sensitive_inputs(inputs, version.canvas_metadata),
        "execution_id": str(execution.id),
        "team": workflow.team[0],
        "actor": {"username": started_by, "domain": domain},
        "__system": _system_context(
            workflow,
            execution_id=str(execution.id),
            version=version.version,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            started_by=started_by,
        ),
    }
    execution.input = redact_sensitive_inputs(conductor_inputs, version.canvas_metadata)
    conductor = client or ConductorClient()
    try:
        conductor_id = conductor.start_workflow(
            workflow.engine_name,
            version=version.version,
            inputs=conductor_inputs,
            correlation_id=str(execution.id),
        )
    except ConductorUnavailable as error:
        execution.status = WorkflowExecution.Status.FAILED
        execution.error_message = str(error)[:500]
        execution.finished_at = timezone.now()
        execution.save(update_fields=("input", "status", "error_message", "finished_at", "updated_at"))
        raise
    execution.conductor_workflow_id = conductor_id
    execution.status = WorkflowExecution.Status.RUNNING
    execution.save(update_fields=("input", "conductor_workflow_id", "status", "updated_at"))
    return execution


@transaction.atomic
def start_debug_execution(
    workflow: Workflow,
    *,
    inputs: dict[str, Any],
    started_by: str,
    domain: str,
    client: ConductorClient | None = None,
    definition_override: dict[str, Any] | None = None,
    canvas_metadata_override: dict[str, Any] | None = None,
    debug_kind: str = WorkflowExecution.DebugKind.FULL,
    debug_task_reference: str = "",
    trigger_type: str = WorkflowTrigger.Type.FORM,
    trigger_id: str = "debug-form",
) -> WorkflowExecution:
    workflow = Workflow.all_objects.select_for_update().get(pk=workflow.pk)
    if workflow.deleted_at is not None:
        raise ValueError("流程已删除，不能创建新调试执行")
    conductor = client or ConductorClient()
    canvas_metadata = copy.deepcopy(canvas_metadata_override if canvas_metadata_override is not None else workflow.canvas_metadata)
    debug_name = f"bklite_debug_{workflow.pk}_{uuid.uuid4().hex}"[:100]
    catalog = available_atom_catalog(workflow.team[0])
    definition = prepare_definition_for_publish(
        definition_override if definition_override is not None else workflow.definition,
        engine_name=debug_name,
        version=1,
        atom_catalog=catalog,
    )
    atom_keys = set()
    for task in _walk_definition_tasks(definition.get("tasks") or []):
        if task.get("type") != "SIMPLE":
            continue
        key = task["name"]
        atom_keys.add(key)
        item = catalog[key]
        if item.get("source_type") == "PLATFORM":
            ensure_platform_atom(
                item,
                username=started_by,
                domain=domain,
            )
    static_task_names = {item["name"] for item in TASK_DEFINITIONS}
    custom_task_definitions = [task_definition_from_catalog_item(catalog[key]) for key in sorted(atom_keys) if key not in static_task_names]
    capability_profiles = capability_resource_snapshot(definition, catalog)
    conductor.register_task_definitions([*TASK_DEFINITIONS, *custom_task_definitions])
    conductor.register_workflow(definition)
    execution = WorkflowExecution.objects.create(
        workflow=workflow,
        workflow_version=0,
        team=workflow.team,
        input=copy.deepcopy(inputs),
        started_by=started_by,
        domain=domain,
        definition_snapshot=copy.deepcopy(definition),
        resource_snapshot={
            "atoms": [{"key": key} for key in sorted(atom_keys)],
            "capability_profiles": capability_profiles,
        },
        mode=WorkflowExecution.Mode.DEBUG,
        debug_kind=debug_kind,
        debug_task_reference=debug_task_reference,
        trigger_type=trigger_type,
        trigger_id=trigger_id,
    )
    conductor_inputs = {
        **seal_sensitive_inputs(inputs, canvas_metadata),
        "execution_id": str(execution.id),
        "team": workflow.team[0],
        "actor": {"username": started_by, "domain": domain},
        "__system": _system_context(
            workflow,
            execution_id=str(execution.id),
            version=0,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            started_by=started_by,
        ),
    }
    execution.input = redact_sensitive_inputs(conductor_inputs, canvas_metadata)
    try:
        conductor_id = conductor.start_workflow(debug_name, version=1, inputs=conductor_inputs, correlation_id=str(execution.id))
    except ConductorUnavailable as error:
        execution.status = WorkflowExecution.Status.FAILED
        execution.error_message = str(error)[:500]
        execution.finished_at = timezone.now()
        execution.save(update_fields=("input", "status", "error_message", "finished_at", "updated_at"))
        raise
    execution.conductor_workflow_id = conductor_id
    execution.status = WorkflowExecution.Status.RUNNING
    execution.save(update_fields=("input", "conductor_workflow_id", "status", "updated_at"))
    return execution

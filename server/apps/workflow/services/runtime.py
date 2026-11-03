from __future__ import annotations

import copy
import uuid
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.workflow.models import Workflow, WorkflowExecution, WorkflowTrigger, WorkflowVersion
from apps.workflow.services.atom_registry import available_atom_catalog, ensure_platform_atom, task_definition_from_catalog_item
from apps.workflow.services.atoms import TASK_DEFINITIONS
from apps.workflow.services.capability_profiles import capability_resource_snapshot
from apps.workflow.services.conductor import ConductorClient, ConductorRejected, ConductorUnavailable, ExecutionStartUnknown
from apps.workflow.services.data_contracts import redact_sensitive_inputs, seal_sensitive_inputs
from apps.workflow.services.definitions import prepare_definition_for_publish

# Unattached QUEUED/UNKNOWN reconcile backoff: 60s * 2^n, capped at 1h.
_RECONCILE_BACKOFF_BASE_SECONDS = 60
_RECONCILE_BACKOFF_MAX_SECONDS = 3600
_UNATTACHED_RECONCILE_STATUSES = frozenset(
    {
        WorkflowExecution.Status.QUEUED,
        WorkflowExecution.Status.UNKNOWN,
    }
)


def _needs_engine_start(execution: WorkflowExecution) -> bool:
    return not execution.conductor_workflow_id and execution.status in {
        WorkflowExecution.Status.QUEUED,
        WorkflowExecution.Status.UNKNOWN,
    }


def _reconcile_backoff_seconds(attempts: int) -> int:
    exponent = max(0, min(int(attempts) - 1, 6))
    return min(_RECONCILE_BACKOFF_MAX_SECONDS, _RECONCILE_BACKOFF_BASE_SECONDS * (2**exponent))


def _schedule_reconcile_backoff(execution: WorkflowExecution) -> WorkflowExecution:
    attempts = int(execution.reconcile_attempts or 0) + 1
    execution.reconcile_attempts = attempts
    execution.reconcile_next_at = timezone.now() + timedelta(seconds=_reconcile_backoff_seconds(attempts))
    execution.save(update_fields=("reconcile_attempts", "reconcile_next_at", "updated_at"))
    return execution


def _clear_reconcile_backoff_fields(execution: WorkflowExecution) -> list[str]:
    changed: list[str] = []
    if execution.reconcile_attempts:
        execution.reconcile_attempts = 0
        changed.append("reconcile_attempts")
    if execution.reconcile_next_at is not None:
        execution.reconcile_next_at = None
        changed.append("reconcile_next_at")
    return changed


def _ensure_engine_definition(conductor: ConductorClient, workflow: Workflow, version: WorkflowVersion) -> None:
    """Publish-time registration can be skipped for builtins or lost when the engine is reset."""

    if conductor.get_workflow_definition(workflow.engine_name, version.version) is not None:
        return
    definition = version.definition if isinstance(version.definition, dict) else {}
    team_id = workflow.team[0] if workflow.team else 0
    catalog = available_atom_catalog(team_id)
    atom_keys = {
        task["name"]
        for task in _walk_definition_tasks(definition.get("tasks") or [])
        if task.get("type") == "SIMPLE" and isinstance(task.get("name"), str)
    }
    static_task_names = {item["name"] for item in TASK_DEFINITIONS}
    custom_task_definitions = [
        task_definition_from_catalog_item(catalog[key]) for key in sorted(atom_keys) if key not in static_task_names and key in catalog
    ]
    conductor.register_task_definitions([*TASK_DEFINITIONS, *custom_task_definitions])
    conductor.register_workflow(definition)


def reconcile_unknown_execution(
    execution: WorkflowExecution,
    *,
    client: ConductorClient | None = None,
    schedule_backoff: bool = True,
) -> WorkflowExecution:
    """Attach a recovered engine id to an unattached QUEUED/UNKNOWN start, or leave it pending.

    Crash window: local row exists as QUEUED/UNKNOWN without conductor_workflow_id while the
    engine may already have accepted start. Sync and launch reuse only correlate — never
    auto-start from the sync path. Empty correlation optionally schedules minimal backoff.
    """

    if execution.conductor_workflow_id or execution.status not in _UNATTACHED_RECONCILE_STATUSES:
        return execution
    conductor = client or ConductorClient()
    workflow_ids = conductor.find_workflow_ids_by_correlation_id(str(execution.id))
    if len(workflow_ids) != 1:
        if schedule_backoff:
            return _schedule_reconcile_backoff(execution)
        return execution
    execution.conductor_workflow_id = workflow_ids[0][:100]
    execution.status = WorkflowExecution.Status.RUNNING
    execution.error_message = ""
    execution.failed_stage = ""
    update_fields = ["conductor_workflow_id", "status", "error_message", "failed_stage", "updated_at"]
    update_fields.extend(_clear_reconcile_backoff_fields(execution))
    execution.save(update_fields=update_fields)
    return execution


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
    entry_input_schema: dict[str, Any] | None = None,
    async_callback_context: dict[str, Any] | None = None,
    async_callback_deadline_at=None,
    async_callback_key: str | None = None,
) -> tuple[WorkflowExecution, WorkflowVersion, bool, dict[str, Any]]:
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
    # Seal/redact before the first durable write so crashes cannot leave plaintext secrets.
    sealed_inputs = seal_sensitive_inputs(inputs, version.canvas_metadata, entry_schema=entry_input_schema)
    redacted_inputs = redact_sensitive_inputs(sealed_inputs, version.canvas_metadata, entry_schema=entry_input_schema)
    defaults = {
        "workflow": workflow,
        "workflow_version": version.version,
        "team": workflow.team,
        "input": copy.deepcopy(redacted_inputs),
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
    if async_callback_context:
        defaults["async_callback_context"] = async_callback_context
        defaults["async_callback_deadline_at"] = async_callback_deadline_at
        defaults["async_callback_key"] = async_callback_key
    if launch_token_hash:
        execution, created = WorkflowExecution.objects.get_or_create(
            launch_token_hash=launch_token_hash,
            defaults=defaults,
        )
        if not created:
            return execution, version, False, sealed_inputs
    else:
        execution = WorkflowExecution.objects.create(**defaults)
    return execution, version, True, sealed_inputs


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
    entry_input_schema: dict[str, Any] | None = None,
    async_callback_context: dict[str, Any] | None = None,
    async_callback_deadline_at=None,
    async_callback_key: str | None = None,
) -> WorkflowExecution:
    execution, version, created, sealed_inputs = _claim_execution(
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
        entry_input_schema=entry_input_schema,
        async_callback_context=async_callback_context,
        async_callback_deadline_at=async_callback_deadline_at,
        async_callback_key=async_callback_key,
    )
    conductor = client or ConductorClient()
    if not created and not _needs_engine_start(execution):
        execution._launch_reused = True
        return execution
    if not created:
        # Launch path decides start vs wait; do not burn reconcile backoff here.
        execution = reconcile_unknown_execution(execution, client=conductor, schedule_backoff=False)
        if execution.conductor_workflow_id:
            execution._launch_reused = True
            return execution
        if execution.status == WorkflowExecution.Status.UNKNOWN:
            # Ambiguous prior start: never call start_workflow again; wait for reconcile.
            execution._launch_reused = True
            raise ExecutionStartUnknown(execution, "启动结果仍未知，请等待对账，禁止重复启动")
    execution._launch_reused = False
    conductor_inputs = {
        **sealed_inputs,
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
    execution.input = redact_sensitive_inputs(
        conductor_inputs,
        version.canvas_metadata,
        entry_schema=entry_input_schema,
    )
    _ensure_engine_definition(conductor, workflow, version)
    try:
        conductor_id = conductor.start_workflow(
            workflow.engine_name,
            version=version.version,
            inputs=conductor_inputs,
            correlation_id=str(execution.id),
        )
    except ConductorRejected as error:
        execution.status = WorkflowExecution.Status.FAILED
        execution.error_message = str(error)[:500]
        execution.failed_stage = "conductor_start"
        execution.finished_at = timezone.now()
        update_fields = ["input", "status", "error_message", "failed_stage", "finished_at", "updated_at"]
        update_fields.extend(_clear_reconcile_backoff_fields(execution))
        execution.save(update_fields=update_fields)
        raise
    except ConductorUnavailable as error:
        # Response loss after engine accept is indistinguishable from reject; keep UNKNOWN for reconcile.
        execution.status = WorkflowExecution.Status.UNKNOWN
        execution.error_message = str(error)[:500]
        execution.failed_stage = "conductor_start"
        update_fields = ["input", "status", "error_message", "failed_stage", "updated_at"]
        update_fields.extend(_clear_reconcile_backoff_fields(execution))
        execution.save(update_fields=update_fields)
        raise ExecutionStartUnknown(execution, str(error)) from error
    execution.conductor_workflow_id = conductor_id
    execution.status = WorkflowExecution.Status.RUNNING
    execution.failed_stage = ""
    update_fields = ["input", "conductor_workflow_id", "status", "failed_stage", "updated_at"]
    update_fields.extend(_clear_reconcile_backoff_fields(execution))
    execution.save(update_fields=update_fields)
    return execution


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
    """Debug starts share production recovery semantics: durable local identity, then remote start."""

    conductor = client or ConductorClient()
    with transaction.atomic():
        workflow = Workflow.all_objects.select_for_update().get(pk=workflow.pk)
        if workflow.deleted_at is not None:
            raise ValueError("流程已删除，不能创建新调试执行")
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
        capability_profiles = capability_resource_snapshot(definition, catalog)
        sealed_inputs = seal_sensitive_inputs(inputs, canvas_metadata)
        redacted_inputs = redact_sensitive_inputs(sealed_inputs, canvas_metadata)
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            workflow_version=0,
            team=workflow.team,
            input=copy.deepcopy(redacted_inputs),
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
            **sealed_inputs,
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
        execution.save(update_fields=("input", "updated_at"))

    static_task_names = {item["name"] for item in TASK_DEFINITIONS}
    custom_task_definitions = [task_definition_from_catalog_item(catalog[key]) for key in sorted(atom_keys) if key not in static_task_names]
    conductor.register_task_definitions([*TASK_DEFINITIONS, *custom_task_definitions])
    conductor.register_workflow(definition)
    try:
        conductor_id = conductor.start_workflow(debug_name, version=1, inputs=conductor_inputs, correlation_id=str(execution.id))
    except ConductorRejected as error:
        execution.status = WorkflowExecution.Status.FAILED
        execution.error_message = str(error)[:500]
        execution.failed_stage = "conductor_start"
        execution.finished_at = timezone.now()
        execution.save(update_fields=("status", "error_message", "failed_stage", "finished_at", "updated_at"))
        raise
    except ConductorUnavailable as error:
        execution.status = WorkflowExecution.Status.UNKNOWN
        execution.error_message = str(error)[:500]
        execution.failed_stage = "conductor_start"
        execution.save(update_fields=("status", "error_message", "failed_stage", "updated_at"))
        raise ExecutionStartUnknown(execution, str(error)) from error
    execution.conductor_workflow_id = conductor_id
    execution.status = WorkflowExecution.Status.RUNNING
    execution.save(update_fields=("conductor_workflow_id", "status", "updated_at"))
    return execution

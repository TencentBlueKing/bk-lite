from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from apps.workflow_orchestration.models import WorkflowExecution, WorkflowInteraction
from apps.workflow_orchestration.services.atoms import ATOM_CATALOG
from apps.workflow_orchestration.services.data_contracts import mask_secret_envelopes

START_REFERENCE = "__start__"
END_REFERENCE = "__end__"

STATE_PRIORITY = {
    "ACTIONABLE": 80,
    "FAILED": 70,
    "TIMED_OUT": 70,
    "RUNNING": 60,
    "WAITING": 50,
    "WARNING": 40,
    "SUCCESS": 30,
    "SKIPPED": 20,
    "UNREACHABLE": 10,
    "PENDING": 0,
}

SYSTEM_NODE_NAMES = {
    "FORK_JOIN": "并行分支",
    "JOIN": "汇聚分支",
    "SWITCH": "条件分支",
    "HUMAN": "人工审批",
}


def _iso(value):
    return value.isoformat() if value else None


def _task_state(status: Any) -> str:
    normalized = str(status or "").upper()
    if normalized in {"FAILED", "FAILED_WITH_TERMINAL_ERROR"}:
        return "FAILED"
    if normalized in {"TIMED_OUT", "TIME_OUT"}:
        return "TIMED_OUT"
    if normalized in {"IN_PROGRESS", "SCHEDULED", "RUNNING"}:
        return "RUNNING"
    if normalized in {"COMPLETED_WITH_ERRORS", "COMPLETED_WITH_WARNINGS"}:
        return "WARNING"
    if normalized in {"COMPLETED", "SUCCESS"}:
        return "SUCCESS"
    if normalized in {"SKIPPED", "CANCELED", "CANCELLED"}:
        return "SKIPPED"
    return "PENDING"


def _interaction_state(interaction: WorkflowInteraction, *, username: str) -> str:
    if interaction.status == WorkflowInteraction.Status.PENDING:
        return "ACTIONABLE" if username in interaction.candidate_users else "WAITING"
    if interaction.status == WorkflowInteraction.Status.APPROVED:
        return "SUCCESS"
    if interaction.status in {WorkflowInteraction.Status.REJECTED, WorkflowInteraction.Status.TIMED_OUT}:
        return "FAILED" if interaction.status == WorkflowInteraction.Status.REJECTED else "TIMED_OUT"
    return "SKIPPED"


def _aggregate_state(states: list[str], *, terminal_execution: bool) -> str:
    if states:
        return max(states, key=lambda state: STATE_PRIORITY.get(state, -1))
    return "UNREACHABLE" if terminal_execution else "PENDING"


def _node_name(task: dict[str, Any]) -> str:
    inputs = task.get("inputParameters") if isinstance(task.get("inputParameters"), dict) else {}
    if task.get("type") == "HUMAN" and str(inputs.get("title") or "").strip():
        return str(inputs["title"])[:120]
    catalog = ATOM_CATALOG.get(str(task.get("name") or ""))
    if catalog:
        return str(catalog["name"])
    return SYSTEM_NODE_NAMES.get(str(task.get("type") or ""), str(task.get("name") or task.get("taskReferenceName") or "节点"))


def _flatten_definition_tasks(
    tasks: list[Any],
    *,
    parent_reference: str | None = None,
    branch_label: str | None = None,
    depth: int = 0,
):
    for raw_task in tasks:
        if not isinstance(raw_task, dict):
            continue
        task = raw_task
        reference = str(task.get("taskReferenceName") or "")
        if not reference:
            continue
        yield task, parent_reference, branch_label, depth
        for index, branch in enumerate(task.get("forkTasks") or [], start=1):
            if isinstance(branch, list):
                yield from _flatten_definition_tasks(
                    branch,
                    parent_reference=reference,
                    branch_label=f"分支 {index}",
                    depth=depth + 1,
                )
        for case, branch in (task.get("decisionCases") or {}).items():
            if isinstance(branch, list):
                yield from _flatten_definition_tasks(
                    branch,
                    parent_reference=reference,
                    branch_label=f"条件 {case}",
                    depth=depth + 1,
                )
        default_case = task.get("defaultCase")
        if isinstance(default_case, list):
            yield from _flatten_definition_tasks(
                default_case,
                parent_reference=reference,
                branch_label="默认分支",
                depth=depth + 1,
            )
        loop_over = task.get("loopOver")
        if isinstance(loop_over, list):
            yield from _flatten_definition_tasks(
                loop_over,
                parent_reference=reference,
                branch_label="循环体",
                depth=depth + 1,
            )


def _runtime_tasks(execution: WorkflowExecution) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in execution.tasks if isinstance(execution.tasks, list) else []:
        if not isinstance(task, dict):
            continue
        reference = str(task.get("reference") or "")
        if reference:
            grouped[reference].append(task)
    return grouped


def _interactions(execution: WorkflowExecution) -> dict[str, list[WorkflowInteraction]]:
    grouped: dict[str, list[WorkflowInteraction]] = defaultdict(list)
    records = list(execution.interactions.all().order_by("created_at", "id"))
    for interaction in records:
        grouped[interaction.task_reference].append(interaction)
    return grouped


def _terminal_execution(execution: WorkflowExecution) -> bool:
    return execution.status in {
        WorkflowExecution.Status.SUCCEEDED,
        WorkflowExecution.Status.FAILED,
        WorkflowExecution.Status.TIMED_OUT,
        WorkflowExecution.Status.TERMINATED,
    }


def build_execution_node_summary(execution: WorkflowExecution, *, username: str) -> dict[str, Any]:
    tasks_by_reference = _runtime_tasks(execution)
    interactions_by_reference = _interactions(execution)
    terminal = _terminal_execution(execution)
    start_state = "PENDING" if execution.status == WorkflowExecution.Status.QUEUED else "SUCCESS"
    nodes = [
        {
            "reference": START_REFERENCE,
            "name": "开始",
            "task_type": "START",
            "task_name": "",
            "parent_reference": None,
            "branch_label": None,
            "depth": 0,
            "state": start_state,
            "state_counts": {start_state: 1},
            "instance_count": 1,
            "actionable_interaction_ids": [],
            "latest_finished_at": None,
        }
    ]
    definition = execution.definition_snapshot if isinstance(execution.definition_snapshot, dict) else {}
    flattened = list(_flatten_definition_tasks(definition.get("tasks") if isinstance(definition.get("tasks"), list) else []))
    for task, parent_reference, branch_label, depth in flattened:
        reference = str(task["taskReferenceName"])
        runtime_instances = tasks_by_reference.get(reference, [])
        interaction_instances = interactions_by_reference.get(reference, [])
        states = [_task_state(instance.get("status")) for instance in runtime_instances]
        states.extend(_interaction_state(interaction, username=username) for interaction in interaction_instances)
        state = _aggregate_state(states, terminal_execution=terminal)
        counts = dict(Counter(states)) if states else {state: 1}
        finished_values = [str(item.get("finished_at")) for item in runtime_instances if item.get("finished_at")]
        actionable_ids = [
            str(interaction.id)
            for interaction in interaction_instances
            if interaction.status == WorkflowInteraction.Status.PENDING and username in interaction.candidate_users
        ]
        nodes.append(
            {
                "reference": reference,
                "name": _node_name(task),
                "task_type": str(task.get("type") or ""),
                "task_name": str(task.get("name") or ""),
                "parent_reference": parent_reference,
                "branch_label": branch_label,
                "depth": depth,
                "state": state,
                "state_counts": counts,
                "instance_count": max(1, len(runtime_instances), len(interaction_instances)),
                "actionable_interaction_ids": actionable_ids,
                "latest_finished_at": max(finished_values) if finished_values else None,
            }
        )
    end_state = {
        WorkflowExecution.Status.SUCCEEDED: "WARNING" if execution.has_warnings else "SUCCESS",
        WorkflowExecution.Status.FAILED: "FAILED",
        WorkflowExecution.Status.TIMED_OUT: "TIMED_OUT",
        WorkflowExecution.Status.TERMINATED: "SKIPPED",
    }.get(execution.status, "PENDING")
    nodes.append(
        {
            "reference": END_REFERENCE,
            "name": "结束",
            "task_type": "END",
            "task_name": "",
            "parent_reference": None,
            "branch_label": None,
            "depth": 0,
            "state": end_state,
            "state_counts": {end_state: 1},
            "instance_count": 1,
            "actionable_interaction_ids": [],
            "latest_finished_at": _iso(execution.finished_at),
        }
    )
    default_node = next((node for node in nodes if node["state"] == "ACTIONABLE"), None)
    if default_node is None:
        default_node = next((node for node in nodes if node["state"] == "RUNNING"), None)
    if default_node is None:
        default_node = next((node for node in nodes if node["state"] in {"FAILED", "TIMED_OUT"}), None)
    if default_node is None:
        completed = [node for node in nodes if node["state"] in {"SUCCESS", "WARNING"}]
        default_node = max(completed, key=lambda node: node["latest_finished_at"] or "") if completed else nodes[0]
    return {"nodes": nodes, "default_node_reference": default_node["reference"]}


def _definition_task(execution: WorkflowExecution, reference: str) -> dict[str, Any] | None:
    definition = execution.definition_snapshot if isinstance(execution.definition_snapshot, dict) else {}
    for task, _, _, _ in _flatten_definition_tasks(definition.get("tasks") if isinstance(definition.get("tasks"), list) else []):
        if task.get("taskReferenceName") == reference:
            return task
    return None


def _interaction_payload(interaction: WorkflowInteraction, *, username: str) -> dict[str, Any]:
    return {
        "id": str(interaction.id),
        "type": interaction.interaction_type,
        "status": interaction.status,
        "title": interaction.title,
        "description": interaction.description,
        "public_context": mask_secret_envelopes(interaction.public_context),
        "candidate_users": interaction.candidate_users,
        "can_act": interaction.status == WorkflowInteraction.Status.PENDING and username in interaction.candidate_users,
        "operator": interaction.operator,
        "decision": interaction.decision,
        "comment": interaction.comment,
        "created_at": _iso(interaction.created_at),
        "due_at": _iso(interaction.due_at),
        "handled_at": _iso(interaction.handled_at),
    }


def _artifact_payload(artifact) -> dict[str, Any]:
    return {
        "id": str(artifact.id),
        "kind": artifact.kind,
        "format": artifact.format,
        "filename": artifact.filename,
        "content_type": artifact.content_type,
        "size": artifact.size,
        "summary": artifact.summary,
        "expires_at": _iso(artifact.expires_at),
        "download_url": f"/workflow_orchestration/api/artifacts/{artifact.id}/download/",
    }


def _control_summary(task: dict[str, Any]) -> dict[str, Any]:
    task_type = str(task.get("type") or "")
    if task_type == "SWITCH":
        return {"condition": task.get("inputParameters") or {}, "branches": list((task.get("decisionCases") or {}).keys())}
    if task_type == "FORK_JOIN":
        return {"branch_count": len(task.get("forkTasks") or [])}
    if task_type == "JOIN":
        return {"join_on": task.get("joinOn") or []}
    return {}


def build_execution_node_detail(
    execution: WorkflowExecution,
    *,
    node_reference: str,
    username: str,
    instance_id: str | None = None,
    include_technical: bool = False,
) -> dict[str, Any] | None:
    summary = build_execution_node_summary(execution, username=username)
    node = next((item for item in summary["nodes"] if item["reference"] == node_reference), None)
    if node is None:
        return None
    if node_reference == START_REFERENCE:
        system_context = execution.input.get("__system") if isinstance(execution.input.get("__system"), dict) else {}
        workflow_inputs = {key: value for key, value in execution.input.items() if key not in {"__system", "execution_id", "team", "actor"}}
        return {
            "node": node,
            "instances": [{"id": START_REFERENCE, "label": "开始"}],
            "selected_instance_id": START_REFERENCE,
            "execution_info": {
                "status": execution.status,
                "trigger_type": execution.trigger_type,
                "started_by": execution.started_by,
                "started_at": _iso(execution.created_at),
            },
            "inputs": mask_secret_envelopes(workflow_inputs),
            "outputs": {},
            "system_context": mask_secret_envelopes(system_context),
            "error": None,
            "audit_events": [{"type": "START", "at": _iso(execution.created_at), "actor": execution.started_by}],
            "artifacts": [],
            "control": {},
            "interaction": None,
            "technical": {"workflow_id": execution.conductor_workflow_id} if include_technical else {},
        }
    if node_reference == END_REFERENCE:
        return {
            "node": node,
            "instances": [{"id": END_REFERENCE, "label": "结束"}],
            "selected_instance_id": END_REFERENCE,
            "execution_info": {
                "status": execution.status,
                "started_at": _iso(execution.created_at),
                "finished_at": _iso(execution.finished_at),
                "duration_ms": int((execution.finished_at - execution.created_at).total_seconds() * 1000) if execution.finished_at else None,
            },
            "inputs": {},
            "outputs": mask_secret_envelopes(execution.output),
            "system_context": {},
            "error": {"message": execution.error_message} if execution.error_message else None,
            "audit_events": ([{"type": "END", "at": _iso(execution.finished_at), "actor": ""}] if execution.finished_at else []),
            "artifacts": [_artifact_payload(artifact) for artifact in execution.artifacts.all()],
            "control": {},
            "interaction": None,
            "technical": {"workflow_id": execution.conductor_workflow_id} if include_technical else {},
        }

    definition_task = _definition_task(execution, node_reference)
    if definition_task is None:
        return None
    interaction_records = list(execution.interactions.filter(task_reference=node_reference).order_by("created_at", "id"))
    if interaction_records:
        instances = [
            {
                "id": str(item.id),
                "label": f"第 {index} 次",
                "state": _interaction_state(item, username=username),
            }
            for index, item in enumerate(interaction_records, start=1)
        ]
        selected = next((item for item in interaction_records if instance_id and str(item.id) == instance_id), None)
        if selected is None:
            selected = next(
                (item for item in interaction_records if item.status == WorkflowInteraction.Status.PENDING and username in item.candidate_users),
                interaction_records[-1],
            )
        return {
            "node": node,
            "instances": instances,
            "selected_instance_id": str(selected.id),
            "execution_info": {
                "status": selected.status,
                "started_at": _iso(selected.created_at),
                "finished_at": _iso(selected.handled_at),
                "duration_ms": int((selected.handled_at - selected.created_at).total_seconds() * 1000) if selected.handled_at else None,
            },
            "inputs": mask_secret_envelopes(selected.public_context),
            "outputs": mask_secret_envelopes(selected.output),
            "system_context": {},
            "error": None,
            "audit_events": [
                {"type": "INTERACTION_CREATED", "at": _iso(selected.created_at), "actor": ""},
                *(
                    [{"type": selected.decision or selected.status, "at": _iso(selected.handled_at), "actor": selected.operator}]
                    if selected.handled_at
                    else []
                ),
            ],
            "artifacts": [],
            "control": {},
            "interaction": _interaction_payload(selected, username=username),
            "technical": {"workflow_id": execution.conductor_workflow_id, "task_id": selected.conductor_task_id} if include_technical else {},
        }

    runtime_instances = _runtime_tasks(execution).get(node_reference, [])
    if not runtime_instances:
        atom_instances = list(execution.atom_executions.filter(task_reference=node_reference).order_by("attempt", "id"))
        runtime_instances = [
            {
                "task_id": item.conductor_task_id or f"atom-{item.id}",
                "status": item.status,
                "worker_id": "",
                "started_at": _iso(item.started_at),
                "finished_at": _iso(item.finished_at),
                "duration_ms": int((item.finished_at - item.started_at).total_seconds() * 1000) if item.started_at and item.finished_at else None,
                "retry_count": max(0, item.attempt - 1),
                "iteration": 0,
                "input": item.input,
                "output": item.output,
                "reason": item.error_message,
                "error_type": item.error_type,
            }
            for item in atom_instances
        ]
    instances = [
        {
            "id": str(item.get("task_id") or f"{node_reference}-{index}"),
            "label": f"第 {index} 次",
            "state": _task_state(item.get("status")),
            "attempt": index,
            "iteration": item.get("iteration", 0),
        }
        for index, item in enumerate(runtime_instances, start=1)
    ]
    selected_index = next((index for index, item in enumerate(instances) if instance_id and item["id"] == instance_id), len(instances) - 1)
    selected = runtime_instances[selected_index] if runtime_instances else None
    artifacts = [
        artifact
        for artifact in execution.artifacts.all()
        if artifact.atom_execution_id and artifact.atom_execution and artifact.atom_execution.task_reference == node_reference
    ]
    if selected is None:
        return {
            "node": node,
            "instances": [],
            "selected_instance_id": None,
            "execution_info": {"status": node["state"]},
            "inputs": {},
            "outputs": {},
            "system_context": {},
            "error": None,
            "audit_events": [],
            "artifacts": [_artifact_payload(artifact) for artifact in artifacts],
            "control": _control_summary(definition_task),
            "interaction": None,
            "technical": {"workflow_id": execution.conductor_workflow_id, "task_reference": node_reference} if include_technical else {},
        }
    selected_state = _task_state(selected.get("status"))
    events = [{"type": "START", "at": selected.get("started_at"), "actor": selected.get("worker_id", "")}]
    if selected.get("retry_count"):
        events.append({"type": "RETRY", "at": selected.get("started_at"), "actor": selected.get("worker_id", "")})
    if selected.get("finished_at"):
        events.append(
            {
                "type": "FAILED" if selected_state in {"FAILED", "TIMED_OUT"} else "END",
                "at": selected.get("finished_at"),
                "actor": selected.get("worker_id", ""),
            }
        )
    return {
        "node": node,
        "instances": instances,
        "selected_instance_id": instances[selected_index]["id"],
        "execution_info": {
            "status": selected_state,
            "started_at": selected.get("started_at"),
            "finished_at": selected.get("finished_at"),
            "duration_ms": selected.get("duration_ms"),
            "retry_count": selected.get("retry_count", 0),
        },
        "inputs": mask_secret_envelopes(selected.get("input") or {}),
        "outputs": mask_secret_envelopes(selected.get("output") or {}),
        "system_context": {},
        "error": (
            {"type": selected.get("error_type") or "", "message": selected.get("reason") or ""} if selected_state in {"FAILED", "TIMED_OUT"} else None
        ),
        "audit_events": events,
        "artifacts": [_artifact_payload(artifact) for artifact in artifacts],
        "control": _control_summary(definition_task),
        "interaction": None,
        "technical": (
            {
                "workflow_id": execution.conductor_workflow_id,
                "task_id": selected.get("task_id") or "",
                "worker_id": selected.get("worker_id") or "",
                "task_reference": node_reference,
            }
            if include_technical
            else {}
        ),
    }

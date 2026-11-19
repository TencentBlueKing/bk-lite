from collections import defaultdict

from apps.itsm.services.ticket.actions import HUMAN_NODE_TYPES, NodeActionValidationError
from apps.itsm.services.ticket.history import current_round_start

_COMPLETIONS = {"submit", "approve", "reject"}
_SUBPROCESS = {"call", "subprocess", "subprocess_submit"}
_BARRIERS = _SUBPROCESS | {"parallel", "parallel_condition", "converge", "inclusive"}
_MULTI = {"any", "all", "serial"}


def _single_human_node(node):
    return node.get("type") in HUMAN_NODE_TYPES and (node.get("multi") or {}).get("mode") not in _MULTI


def _belongs_to_main_process(ticket, task, has_subprocess):
    if task.process_instance_id:
        return task.process_instance_id == ticket.process_instance_id
    return not has_subprocess


def _eligible_ancestors(design, nodes, current):
    incoming = defaultdict(list)
    for edge in design.get("edges", []):
        incoming[edge.get("to")].append(edge.get("from"))
    visited = {current}
    candidates = set()
    stack = list(incoming[current])
    while stack:
        node_id = stack.pop()
        if node_id in visited or node_id not in nodes:
            continue
        visited.add(node_id)
        node = nodes[node_id]
        if node.get("type") in _BARRIERS:
            continue
        if _single_human_node(node):
            candidates.add(node_id)
        stack.extend(incoming[node_id])
    return candidates


def return_targets(ticket, task, tasks, design, round_start):
    if round_start and task.created_at < round_start:
        return []
    nodes = {node.get("id"): node for node in design.get("nodes", [])}
    current_node = nodes.get(task.node_id, {})
    has_subprocess = any(node.get("type") in _SUBPROCESS for node in nodes.values())
    active = [row for row in tasks if row.status in {"pending", "claimed"}]
    multi = (current_node.get("multi") or {}).get("mode") in _MULTI
    if (
        current_node.get("type") not in HUMAN_NODE_TYPES
        or not active
        or (len(active) > 1 and not multi)
        or any(row.node_id != task.node_id or not _belongs_to_main_process(ticket, row, has_subprocess) for row in active)
    ):
        return []
    eligible = _eligible_ancestors(design, nodes, task.node_id)
    if not eligible:
        return []
    completed = {
        row.pk: row
        for row in tasks
        if row.status == "done"
        and row.node_id in eligible
        and _belongs_to_main_process(ticket, row, has_subprocess)
        and (round_start is None or row.created_at >= round_start)
    }
    logs = sorted(ticket.logs.all(), key=lambda row: (row.created_at, row.pk), reverse=True)
    targets = {}
    for log in logs:
        historic = completed.get(log.task_id)
        if historic is None or log.action not in _COMPLETIONS or log.created_at > task.created_at or (round_start and log.created_at < round_start):
            continue
        targets.setdefault(
            historic.node_id,
            {
                "node_id": historic.node_id,
                "name": nodes[historic.node_id].get("name") or historic.node_name or historic.node_id,
                "completed_at": log.created_at.isoformat(),
            },
        )
    return list(targets.values())


def resolve_return_target(ticket, task, design, data, automatic=False):
    submit = next((node for node in design.get("nodes", []) if node.get("type") == "submit"), {})
    submit_id = submit.get("id")
    if automatic and submit_id:
        return {"node_id": submit_id, "name": submit.get("name") or submit_id}
    tasks = list(ticket.tasks.all())
    targets = return_targets(ticket, task, tasks, design, current_round_start(ticket, tasks, design))
    if "return_node_id" in data:
        requested = data["return_node_id"]
    elif data.get("return_mode") == "previous":
        requested = targets[0]["node_id"] if targets else None
    elif data.get("return_mode") == "submit":
        requested = submit_id
    else:
        raise NodeActionValidationError("请选择可回退的历史节点")
    target = next((row for row in targets if row["node_id"] == requested), None)
    if target is None:
        raise NodeActionValidationError("所选节点不可回退，请刷新并选择本轮已完成的历史节点")
    return target

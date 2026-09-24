from __future__ import annotations

import copy
from collections import defaultdict, deque
from typing import Any

from apps.workflow_orchestration.services.definitions import DefinitionValidationError


def _descendants(start: str, adjacency: dict[str, list[str]]) -> dict[str, int]:
    distances = {start: 0}
    pending = deque([start])
    while pending:
        current = pending.popleft()
        for target in adjacency.get(current, []):
            if target not in distances:
                distances[target] = distances[current] + 1
                pending.append(target)
    return distances


def _convergence(successors: list[str], adjacency: dict[str, list[str]]) -> str | None:
    distances = [_descendants(item, adjacency) for item in successors]
    common = set(distances[0])
    for item in distances[1:]:
        common.intersection_update(item)
    if not common:
        return None
    return min(common, key=lambda node: (max(item[node] for item in distances), sum(item[node] for item in distances), node))


def compile_canvas_graph(definition: Any, canvas_metadata: Any) -> dict[str, Any]:  # noqa: C901
    """Compile the user-authored edge DAG into Conductor's structured task DSL.

    The authored definition contains business/control nodes only. FORK_JOIN and JOIN
    are compiler implementation details and are emitted only into executable snapshots.
    """
    if not isinstance(definition, dict) or not isinstance(canvas_metadata, dict):
        raise DefinitionValidationError("流程定义和画布元数据必须是 JSON 对象")
    if canvas_metadata.get("control_flow_mode") != "EDGES":
        return copy.deepcopy(definition)

    authored = definition.get("tasks")
    if not isinstance(authored, list):
        raise DefinitionValidationError("Conductor DSL 至少需要一个 tasks 节点")
    if any(task.get("type") in {"FORK_JOIN", "JOIN"} or task.get("forkTasks") for task in authored if isinstance(task, dict)):
        raise DefinitionValidationError("连线模式不允许手工配置 FORK_JOIN/JOIN")

    task_map = {
        task.get("taskReferenceName"): copy.deepcopy(task)
        for task in authored
        if isinstance(task, dict) and isinstance(task.get("taskReferenceName"), str)
    }
    if len(task_map) != len(authored):
        raise DefinitionValidationError("连线模式要求所有业务节点位于画布顶层且引用唯一")
    if not task_map:
        return copy.deepcopy(definition)

    trigger_ids = {item.get("id") for item in canvas_metadata.get("trigger_nodes", []) if isinstance(item, dict)}
    return_ids = {item.get("id") for item in canvas_metadata.get("return_nodes", []) if isinstance(item, dict)}
    adjacency: dict[str, list[str]] = defaultdict(list)
    terminal_adjacency: dict[str, list[str]] = defaultdict(list)
    edge_handles: dict[tuple[str, str], str | None] = {}
    entries: list[str] = []
    for edge in canvas_metadata.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("source"), edge.get("target")
        if source in trigger_ids and target in task_map and target not in entries:
            entries.append(target)
        if source in task_map and target in task_map and target not in adjacency[source]:
            adjacency[source].append(target)
            edge_handles[(source, target)] = edge.get("sourceHandle")
        if source in task_map and target in return_ids and target not in terminal_adjacency[source]:
            terminal_adjacency[source].append(target)
            edge_handles[(source, target)] = edge.get("sourceHandle")
    if len(entries) != 1:
        raise DefinitionValidationError("连线模式要求所有触发器进入同一个首节点")

    emitted: set[str] = set()

    def compile_sequence(start: str, stop: str | None = None) -> tuple[list[dict[str, Any]], str]:
        result: list[dict[str, Any]] = []
        current = start
        last = start
        while current != stop:
            if current in emitted:
                raise DefinitionValidationError(f"画布分支不是可结构化的 DAG，节点 {current} 被多条路径重复进入")
            emitted.add(current)
            task = copy.deepcopy(task_map[current])
            successors = adjacency.get(current, [])
            terminal_successors = terminal_adjacency.get(current, [])
            last = current
            if len(successors) + len(terminal_successors) <= 1:
                result.append(task)
                if not successors or successors[0] == stop:
                    break
                current = successors[0]
                continue

            if task.get("type") != "SWITCH" and terminal_successors:
                raise DefinitionValidationError(f"节点 {current} 只有条件分支可以同时连接响应节点和后续任务")

            convergence = _convergence(successors, adjacency) if successors and not terminal_successors else None
            if stop is not None and convergence is None:
                convergence = stop
            branches: list[tuple[str, list[dict[str, Any]], str]] = []
            for successor in successors:
                branch, terminal = compile_sequence(successor, convergence)
                if not branch and task.get("type") != "SWITCH":
                    raise DefinitionValidationError(f"节点 {current} 存在空分支")
                label = str(edge_handles.get((current, successor)) or len(branches))
                branches.append((label, branch, terminal))
            for terminal in terminal_successors:
                label = str(edge_handles.get((current, terminal)) or len(branches))
                branches.append((label, [], current))

            if task.get("type") == "SWITCH":
                cases = {label: branch for label, branch, _ in branches}
                task["decisionCases"] = cases
                task["defaultCase"] = []
                result.append(task)
            else:
                result.append(task)
                fork_reference = f"__auto_fork_{current}"
                join_reference = f"__auto_join_{current}"
                result.extend(
                    [
                        {
                            "name": "__auto_parallel",
                            "taskReferenceName": fork_reference,
                            "type": "FORK_JOIN",
                            "forkTasks": [branch for _, branch, _ in branches],
                        },
                        {
                            "name": "__auto_join",
                            "taskReferenceName": join_reference,
                            "type": "JOIN",
                            "joinOn": [terminal for _, _, terminal in branches],
                        },
                    ]
                )
                last = join_reference
            if convergence is None or convergence == stop:
                break
            current = convergence
        return result, last

    compiled_tasks, _ = compile_sequence(entries[0])
    missing = set(task_map).difference(emitted)
    if missing:
        raise DefinitionValidationError(f"画布存在无法编译的节点: {', '.join(sorted(missing))}")
    compiled = copy.deepcopy(definition)
    compiled["tasks"] = compiled_tasks
    return compiled

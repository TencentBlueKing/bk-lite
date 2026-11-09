from typing import Any

from apps.itsm.services.form.rules import match_when


def next_user_tasks(design: dict[str, Any], current_node_id: str, variables: dict[str, Any]) -> list[dict[str, Any]]:
    """按当前变量求值出边，返回下一批人工节点。"""
    nodes = {node["id"]: node for node in design.get("nodes") or []}
    edges = design.get("edges") or []
    queue = [current_node_id]
    found = []
    seen = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        outgoing = [edge for edge in edges if edge.get("from") == node_id]
        chosen = []
        for edge in outgoing:
            if edge.get("default"):
                continue
            condition = edge.get("condition")
            if condition is None or match_when(condition, variables):
                chosen.append(edge)
        if not chosen:
            chosen = [edge for edge in outgoing if edge.get("default")]
        for edge in chosen:
            target = nodes.get(edge.get("to"))
            if not target:
                continue
            if target.get("type") in {"submit", "approval", "handle"}:
                found.append(target)
            else:
                queue.append(target["id"])
    return found

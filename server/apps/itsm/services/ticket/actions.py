"""节点操作配置是展示与执行共同使用的契约。"""
TASK_ACTIONS = {"submit", "approve", "reject", "claim", "save", "return", "transfer"}


def node_actions(node, task):
    supported = {"approve", "reject"} if node.get("type") == "approval" else {"submit"}
    supported.update({"claim", "save", "transfer"})
    if node.get("type") != "submit":
        supported.add("return")
    if task.status != "pending":
        supported.discard("claim")
    configured = node.get("actions")
    return sorted(supported if configured is None else supported.intersection(configured))


def side_action_enabled(design, tasks, action):
    if action == "reopen":
        return True
    active_ids = {task.node_id for task in tasks if task.status in {"pending", "claimed"}}
    nodes = [node for node in design.get("nodes", []) if node.get("id") in active_ids]
    configured_action = "suspend" if action == "resume" else action
    return any(node.get("actions") is None or configured_action in node["actions"] for node in nodes) if nodes else True

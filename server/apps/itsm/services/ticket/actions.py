"""节点操作配置是展示与执行共同使用的契约。"""
TASK_ACTIONS = {"submit", "approve", "reject", "claim", "save", "return", "transfer"}
SIDE_OPINION_ACTIONS = {"withdraw", "urge", "suspend", "close", "terminate"}
HUMAN_NODE_TYPES = {"submit", "approval", "handle", "manual", "manual_trigger", "subprocess_handle"}
OPINION_LENGTH_LIMIT = 2000
ACTION_LABEL_LENGTH_LIMIT = 24


class NodeActionValidationError(ValueError):
    pass


def _supported_task_actions(node_type):
    supported = {"approve", "reject"} if node_type == "approval" else {"submit"}
    supported.update({"claim", "save", "transfer"})
    if node_type != "submit":
        supported.add("return")
    return supported


def node_actions(node, task):
    supported = _supported_task_actions(node.get("type"))
    if task.status != "pending":
        supported.discard("claim")
    configured = node.get("actions")
    return sorted(supported if configured is None else supported.intersection(configured))


def _active_nodes(design, tasks):
    active_ids = {task.node_id for task in tasks if task.status in {"pending", "claimed"}}
    return [node for node in design.get("nodes", []) if node.get("id") in active_ids]


def _side_action_key(action):
    return "suspend" if action == "resume" else action


def side_action_enabled(design, tasks, action):
    if action == "reopen":
        return True
    nodes = _active_nodes(design, tasks)
    configured_action = _side_action_key(action)
    return any(node.get("actions") is None or configured_action in node["actions"] for node in nodes) if nodes else True


def _required_opinions(node):
    settings = node.get("required_opinion_actions", [])
    return {action for action in settings if isinstance(action, str)} if isinstance(settings, list) else set()


def _enabled_node_actions(node):
    node_type = node.get("type")
    supported = _supported_task_actions(node_type) | SIDE_OPINION_ACTIONS if node_type in HUMAN_NODE_TYPES else set()
    enabled = node.get("actions")
    return supported if enabled is None else supported.intersection(enabled)


def configured_action_display(node):
    display = node.get("action_display", [])
    if not isinstance(display, list):
        raise ValueError("按钮展示设置必须为列表")
    if not display:
        return []
    enabled = _enabled_node_actions(node)
    seen = set()
    entries = []
    for entry in display:
        if not isinstance(entry, dict) or not isinstance(entry.get("action"), str) or entry.keys() - {"action", "label"}:
            raise ValueError("按钮展示设置只能包含动作标识和名称")
        action = entry["action"]
        if action not in enabled or action in seen:
            raise ValueError("按钮展示设置只能使用当前节点已启用的按钮，且不可重复")
        label = entry.get("label", "")
        if not isinstance(label, str):
            raise ValueError("按钮名称必须为文本")
        label = label.strip()
        if len(label) > ACTION_LABEL_LENGTH_LIMIT or len(label.splitlines()) > 1:
            raise ValueError(f"按钮名称须为不超过 {ACTION_LABEL_LENGTH_LIMIT} 字的单行文本")
        seen.add(action)
        entries.append({"action": action, "label": label} if label else {"action": action})
    return entries


def node_action_display(node, available):
    if not available:
        return []
    try:
        entries = configured_action_display(node)
    except ValueError:
        return []
    available_ids = {_side_action_key(action): action for action in available}
    result = []
    for entry in entries:
        action = available_ids.get(entry["action"])
        if action:
            result.append(entry if action == entry["action"] else {"action": action})
    return result


def validate_opinion_settings(node):
    configured = node.get("required_opinion_actions", [])
    if not isinstance(configured, list) or any(not isinstance(action, str) for action in configured):
        raise ValueError("处理意见必填设置必须是按钮列表")
    if not configured:
        return
    if len(set(configured)) != len(configured) or not set(configured).issubset(_enabled_node_actions(node)):
        raise ValueError("处理意见必填设置只能使用当前节点已启用的按钮，且不可重复")


def node_required_opinions(node, available):
    return sorted(_required_opinions(node).intersection(available))


def side_required_opinions(design, tasks, available):
    return sorted(
        action
        for action in available
        if _side_action_key(action) in SIDE_OPINION_ACTIONS
        and any(
            _side_action_key(action) in _required_opinions(node) and (node.get("actions") is None or _side_action_key(action) in node["actions"])
            for node in _active_nodes(design, tasks)
        )
    )


def validated_opinion(opinion, required=False):
    if not isinstance(opinion, str) or len(opinion) > OPINION_LENGTH_LIMIT:
        raise NodeActionValidationError(f"处理意见须为不超过 {OPINION_LENGTH_LIMIT} 字的文本")
    opinion = opinion.strip()
    if required and not opinion:
        raise NodeActionValidationError("请填写处理意见")
    return opinion

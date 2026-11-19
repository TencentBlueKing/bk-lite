"""节点操作配置是展示与执行共同使用的契约。"""
TASK_ACTIONS = {"submit", "approve", "reject", "claim", "save", "return", "transfer"}
SIDE_OPINION_ACTIONS = {"withdraw", "urge", "suspend", "close", "terminate"}
HUMAN_NODE_TYPES = {"submit", "approval", "handle", "manual", "manual_trigger", "subprocess_handle"}
OPINION_LENGTH_LIMIT = 2000


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


def validate_opinion_settings(node):
    configured = node.get("required_opinion_actions", [])
    if not isinstance(configured, list) or any(not isinstance(action, str) for action in configured):
        raise ValueError("处理意见必填设置必须是按钮列表")
    if not configured:
        return
    node_type = node.get("type")
    supported = _supported_task_actions(node_type) | SIDE_OPINION_ACTIONS if node_type in HUMAN_NODE_TYPES else set()
    enabled = node.get("actions")
    if enabled is not None:
        supported.intersection_update(enabled)
    if len(set(configured)) != len(configured) or not set(configured).issubset(supported):
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

from apps.itsm.flowable.design_schema import PHASE1_TYPES, DesignDocument
from apps.itsm.services.ticket.actions import configured_action_display, validate_opinion_settings


def validate_design(payload: dict) -> list[str]:
    """发布前校验。返回中文错误，空列表表示可以通过。"""
    document = DesignDocument.model_validate(payload)
    errors: list[str] = []
    nodes = document.node_map()
    field_keys = set(document.settings.get("fields") or [])
    linked = set()
    for edge in document.edges:
        if edge.from_ not in nodes or edge.to not in nodes:
            errors.append("连线指向不存在的节点")
            continue
        linked.add(edge.from_)
        linked.add(edge.to)
    if not any(node.type == "end" for node in document.nodes):
        errors.append("缺少结束节点")
    for raw_node, node in zip(payload["nodes"], document.nodes):
        for validate in (validate_opinion_settings, configured_action_display):
            try:
                validate(raw_node)
            except ValueError as exc:
                errors.append(f"节点 {node.name or node.id}：{exc}")
        if node.type in {"manual_trigger", "rule_trigger"}:
            config = node.auto or {}
            kind = config.get("kind")
            if (
                kind not in {"table", "http", "integration"}
                or (kind == "table" and not config.get("table_key"))
                or (kind == "http" and not config.get("url"))
            ):
                errors.append(f"节点 {node.name or node.id} 需要配置执行动作")
        if node.type in {"auto", "manual_trigger", "rule_trigger"} and (node.auto or {}).get("kind") == "integration":
            if not (node.auto or {}).get("integration_id") or not isinstance((node.auto or {}).get("inputs", {}), dict):
                errors.append(f"节点 {node.id} 需要选择集成并配置有效 JSON 参数")
        if node.type not in PHASE1_TYPES:
            errors.append(f"节点 {node.id} 的类型 {node.type} 第一期不支持")
        if node.id not in linked and len(document.nodes) > 1:
            errors.append(f"节点 {node.id} 是孤立节点")
        if node.type in {"approval", "handle", "manual", "manual_trigger", "subprocess_handle"} and not node.assignee and not node.fallback:
            errors.append(f"节点 {node.id} 处理人为空且没有兜底")
        for key, mode in node.field_perm.items():
            if mode not in {"edit", "editable", "read", "readonly", "hidden", "required"}:
                errors.append(f"节点 {node.id} 字段 {key} 的权限无效")
            if key != "*" and field_keys and key not in field_keys:
                errors.append(f"节点 {node.id} 引用了不存在的字段 {key}")
    for node in document.nodes:
        if node.type not in {"exclusive", "branch", "branch_condition", "parallel_condition"}:
            continue
        outgoing = [edge for edge in document.edges if edge.from_ == node.id]
        if not any(edge.default for edge in outgoing):
            errors.append(f"条件节点 {node.id} 没有默认分支")
    return errors

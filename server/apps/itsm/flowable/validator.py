from apps.itsm.flowable.design_schema import PHASE1_TYPES, DesignDocument


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
    for node in document.nodes:
        if node.type not in PHASE1_TYPES:
            errors.append(f"节点 {node.id} 的类型 {node.type} 第一期不支持")
        if node.id not in linked and len(document.nodes) > 1:
            errors.append(f"节点 {node.id} 是孤立节点")
        if node.type in {"approval", "handle", "manual", "subprocess_handle"} and not node.assignee and not node.fallback:
            errors.append(f"节点 {node.id} 处理人为空且没有兜底")
        for key, mode in node.field_perm.items():
            if mode not in {"edit", "editable", "read", "readonly", "hidden", "required"}:
                errors.append(f"节点 {node.id} 字段 {key} 的权限无效")
            if key != "*" and field_keys and key not in field_keys:
                errors.append(f"节点 {node.id} 引用了不存在的字段 {key}")
    for node in document.nodes:
        if node.type not in {"exclusive", "branch", "branch_condition"}:
            continue
        outgoing = [edge for edge in document.edges if edge.from_ == node.id]
        if not any(edge.default for edge in outgoing):
            errors.append(f"条件节点 {node.id} 没有默认分支")
    return errors

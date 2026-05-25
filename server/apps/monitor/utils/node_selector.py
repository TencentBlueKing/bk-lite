from apps.core.exceptions.base_app_exception import BaseAppException


SUPPORTED_NODE_SELECTOR_KEYS = {"is_container"}


def normalize_node_selector(node_selector):
    if node_selector in (None, ""):
        return {}

    if not isinstance(node_selector, dict):
        raise BaseAppException("node_selector 配置必须是对象")

    unsupported_keys = sorted(set(node_selector) - SUPPORTED_NODE_SELECTOR_KEYS)
    if unsupported_keys:
        raise BaseAppException(f"node_selector 暂不支持字段: {', '.join(unsupported_keys)}")

    normalized = {}
    if "is_container" in node_selector:
        value = node_selector.get("is_container")
        if not isinstance(value, bool):
            raise BaseAppException("node_selector.is_container 必须是布尔值")
        normalized["is_container"] = value

    return normalized


def merge_node_query_with_selector(query_data, node_selector):
    selector = normalize_node_selector(node_selector)
    if not selector:
        return query_data

    merged_query = dict(query_data)
    for key, value in selector.items():
        current_value = merged_query.get(key)
        if current_value in (None, ""):
            merged_query[key] = value
            continue
        if current_value != value:
            raise BaseAppException("当前插件限制了可选节点范围")

    return merged_query

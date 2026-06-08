from typing import Dict, Iterable, Tuple

DEFAULT_MEMORY_WRITE_BATCH_SIZE = 30


def normalize_write_batch_size(value) -> int:
    """规范化批量写入条数配置"""
    try:
        batch_size = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MEMORY_WRITE_BATCH_SIZE
    return max(1, batch_size)


def build_memory_target_id(owner_username: str, owner_domain: str = "", organization_id: int = None) -> str:
    """构造缓存筛选用的记忆对象 ID"""
    if organization_id is not None:
        return str(organization_id)
    if owner_domain:
        return f"{owner_username}@{owner_domain}"
    return owner_username


def build_batch_content(items: Iterable) -> str:
    """按时间顺序拼接批量缓存内容"""
    contents = [item.content for item in items if getattr(item, "content", "")]
    return "\n\n---\n\n".join(contents)


def extract_memory_write_node_configs(flow_json) -> Dict[str, dict]:
    """提取 workflow 中 memory_write 节点配置"""
    if not isinstance(flow_json, dict):
        return {}

    node_configs = {}
    for node in flow_json.get("nodes", []):
        if node.get("type") != "memory_write":
            continue
        node_id = node.get("id")
        if not node_id:
            continue
        config = node.get("data", {}).get("config", {}) or {}
        node_configs[node_id] = config
    return node_configs


def find_memory_write_nodes_to_flush(old_flow_json, new_flow_json) -> Dict[str, dict]:
    """找出因切换/删除记忆对象而需要先 flush 的旧节点配置"""
    old_nodes = extract_memory_write_node_configs(old_flow_json)
    new_nodes = extract_memory_write_node_configs(new_flow_json)

    flush_nodes = {}
    for node_id, old_config in old_nodes.items():
        old_space = old_config.get("memorySpace") or old_config.get("memory_space_id")
        if not old_space:
            continue

        new_config = new_nodes.get(node_id)
        new_space = None
        if new_config:
            new_space = new_config.get("memorySpace") or new_config.get("memory_space_id")

        if not new_config or str(old_space) != str(new_space):
            flush_nodes[node_id] = old_config

    return flush_nodes


def resolve_memory_target(memory_space, memory_target_id: str) -> Tuple[str, str, int]:
    """从缓存 target_id 还原记忆写入目标"""
    if memory_space.scope == memory_space.SCOPE_TEAM:
        return "", "", int(memory_target_id)

    if "@" in memory_target_id:
        owner_username, owner_domain = memory_target_id.rsplit("@", 1)
        return owner_username, owner_domain, None

    return memory_target_id, "", None

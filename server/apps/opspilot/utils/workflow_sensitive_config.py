from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.core.mixinx import EncryptMixin

MASKED_SECRET_VALUE = "******"
ENTERPRISE_WECHAT_AIBOT_NODE_TYPE = "enterprise_wechat_aibot"

_SENSITIVE_FIELD_PATHS = (
    ("webhook", "token"),
    ("webhook", "encodingAESKey"),
    ("websocket", "secret"),
)


def _iter_aibot_nodes(workflow_data: dict[str, Any]):
    for node in workflow_data.get("nodes", []) or []:
        if isinstance(node, dict) and node.get("type") == ENTERPRISE_WECHAT_AIBOT_NODE_TYPE:
            yield node


def _get_config(node: dict[str, Any]) -> dict[str, Any]:
    data = node.get("data") or {}
    return data.get("config") or {}


def _get_sensitive_parent(config: dict[str, Any], parent_key: str) -> dict[str, Any] | None:
    parent = config.get(parent_key)
    return parent if isinstance(parent, dict) else None


def _apply_to_sensitive_fields(workflow_data: dict[str, Any], callback) -> None:
    for node in _iter_aibot_nodes(workflow_data):
        config = _get_config(node)
        for parent_key, field_name in _SENSITIVE_FIELD_PATHS:
            parent = _get_sensitive_parent(config, parent_key)
            if not parent or not parent.get(field_name) or parent.get(field_name) == MASKED_SECRET_VALUE:
                continue
            callback(parent, field_name)


def encrypt_workflow_sensitive_config(workflow_data):
    """加密 workflow 中企微智能机器人节点的敏感凭据。"""
    if not isinstance(workflow_data, dict):
        return workflow_data

    result = deepcopy(workflow_data)

    def _encrypt(parent: dict[str, Any], field_name: str) -> None:
        EncryptMixin.decrypt_field(field_name, parent)
        EncryptMixin.encrypt_field(field_name, parent)

    _apply_to_sensitive_fields(result, _encrypt)
    return result


def decrypt_workflow_sensitive_config(workflow_data):
    """解密 workflow 中企微智能机器人节点的敏感凭据，供运行时使用。"""
    if not isinstance(workflow_data, dict):
        return workflow_data

    result = deepcopy(workflow_data)
    _apply_to_sensitive_fields(result, lambda parent, field_name: EncryptMixin.decrypt_field(field_name, parent))
    return result


def mask_workflow_sensitive_config(workflow_data):
    """隐藏 workflow 中企微智能机器人节点的敏感凭据，供 API 回显使用。"""
    if not isinstance(workflow_data, dict):
        return workflow_data

    result = deepcopy(workflow_data)

    def _mask(parent: dict[str, Any], field_name: str) -> None:
        parent[field_name] = MASKED_SECRET_VALUE

    _apply_to_sensitive_fields(result, _mask)
    return result


def _node_key(node: dict[str, Any], index: int) -> str:
    return str(node.get("id") or f"__index_{index}")


def _existing_node_map(existing_workflow_data) -> dict[str, dict[str, Any]]:
    if not isinstance(existing_workflow_data, dict):
        return {}
    decrypted = decrypt_workflow_sensitive_config(existing_workflow_data)
    return {_node_key(node, index): node for index, node in enumerate(decrypted.get("nodes", []) or []) if isinstance(node, dict)}


def merge_masked_workflow_sensitive_config(submitted_workflow_data, existing_workflow_data):
    """保存带掩码的 workflow 时，保留原有敏感字段并加密新值。"""
    if not isinstance(submitted_workflow_data, dict):
        return submitted_workflow_data

    result = deepcopy(submitted_workflow_data)
    existing_nodes = _existing_node_map(existing_workflow_data)

    for index, node in enumerate(result.get("nodes", []) or []):
        if not isinstance(node, dict) or node.get("type") != ENTERPRISE_WECHAT_AIBOT_NODE_TYPE:
            continue

        existing_node = existing_nodes.get(_node_key(node, index))
        if not existing_node:
            continue

        config = _get_config(node)
        existing_config = _get_config(existing_node)
        for parent_key, field_name in _SENSITIVE_FIELD_PATHS:
            parent = _get_sensitive_parent(config, parent_key)
            existing_parent = _get_sensitive_parent(existing_config, parent_key)
            if parent and existing_parent and parent.get(field_name) == MASKED_SECRET_VALUE and existing_parent.get(field_name):
                parent[field_name] = existing_parent[field_name]

    return encrypt_workflow_sensitive_config(result)

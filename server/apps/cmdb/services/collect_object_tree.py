from copy import deepcopy

from apps.cmdb.collect.extensions import get_collect_enterprise_extension
from apps.cmdb.constants.constants import COLLECT_OBJ_TREE


def _get_enterprise_collect_obj_tree():
    return deepcopy(get_collect_enterprise_extension().collect_tree)


def _normalize_enterprise_groups(enterprise_tree):
    if not enterprise_tree:
        return []
    if isinstance(enterprise_tree, dict):
        return [enterprise_tree]
    if isinstance(enterprise_tree, list):
        return enterprise_tree
    return []


def _normalize_enterprise_children(children):
    if not children:
        return []
    if isinstance(children, dict):
        return [children]
    if isinstance(children, list):
        return children
    return []


def get_collect_obj_tree():
    tree = deepcopy(COLLECT_OBJ_TREE)
    enterprise_tree = _get_enterprise_collect_obj_tree()

    category_map = {item.get("id"): item for item in tree}
    for enterprise_group in _normalize_enterprise_groups(enterprise_tree):
        category_id = enterprise_group.get("id")
        if not category_id:
            continue
        category = category_map.get(category_id)
        if category is None:
            continue

        existing_children = category.setdefault("children", [])
        existing_model_ids = {child.get("model_id"): index for index, child in enumerate(existing_children)}

        for child in _normalize_enterprise_children(enterprise_group.get("children")):
            model_id = child.get("model_id")
            if not model_id:
                continue
            if model_id in existing_model_ids:
                existing_children[existing_model_ids[model_id]] = child
                continue
            existing_children.append(child)

    return tree


def get_collect_object_meta(collect_model_id: str, driver_type: str | None = None):
    fallback = {}
    for parent in get_collect_obj_tree():
        for child in parent.get("children", []):
            if child.get("model_id") == collect_model_id:
                if driver_type is None:
                    return child
                if child.get("type") == driver_type:
                    return child
                # 同一个 model_id 现在可能对应多条采集入口（如 physcial_server/job 与 physcial_server/protocol）。
                # 如果调用方没有精确命中 driver_type，则保留第一个入口作为兼容回退结果。
                if not fallback:
                    fallback = child
    return fallback

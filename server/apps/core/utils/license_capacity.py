"""社区版入口。没有企业容量模块时保持原权限和菜单。"""

try:
    from apps.license_mgmt.services.capacity_service import (
        filter_menu_tree as _filter_menu_tree,
        filter_permission_map as _filter_permission_map,
    )
except ImportError:
    _filter_menu_tree = None
    _filter_permission_map = None


def filter_permission_map(permissions: dict) -> dict:
    if _filter_permission_map is None:
        return permissions
    return _filter_permission_map(permissions)


def filter_menu_tree(app: str, tree: list) -> list:
    if _filter_menu_tree is None:
        return tree
    return _filter_menu_tree(app, tree)

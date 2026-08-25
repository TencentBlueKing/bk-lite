from copy import deepcopy
from dataclasses import dataclass

from django.db import transaction

from apps.system_mgmt.models import CustomMenuGroup, Menu, Role

PATCH_APP = "patch"
LEGACY_SETTINGS_URL = "/patch-manager/settings"
SETTINGS_PARENT_NAME = "patch_settings"
SOURCE_MENU_NAME = "patch_source"
SCAN_MENU_NAME = "patch_scan_setting"
SOURCE_SETTINGS_URL = "/patch-manager/settings/sources"
SCAN_SETTINGS_URL = "/patch-manager/settings/scan"
PERMISSION_MAPPING = {
    "patch_source-View": "patch_scan_setting-View",
    "patch_source-Edit": "patch_scan_setting-Edit",
}


@dataclass(frozen=True)
class PatchSettingsSplitMigrationResult:
    roles_updated: int
    custom_menu_groups_updated: int


@transaction.atomic
def migrate_patch_settings_split() -> PatchSettingsSplitMigrationResult:
    """迁移补丁设置拆分后的角色授权与自定义菜单，支持重复执行。"""
    permission_names = [*PERMISSION_MAPPING, *PERMISSION_MAPPING.values()]
    permission_ids = dict(Menu.objects.filter(app=PATCH_APP, name__in=permission_names).values_list("name", "id"))
    missing_permissions = sorted(set(permission_names) - set(permission_ids))
    if missing_permissions:
        raise RuntimeError(f"补丁设置权限资源不完整: {', '.join(missing_permissions)}")

    changed_roles = _migrate_roles(permission_ids)
    changed_groups = _migrate_custom_menu_groups()
    return PatchSettingsSplitMigrationResult(
        roles_updated=len(changed_roles),
        custom_menu_groups_updated=len(changed_groups),
    )


@transaction.atomic
def reverse_patch_settings_split_custom_menus() -> PatchSettingsSplitMigrationResult:
    """回滚自定义菜单结构；权限资源和角色失效 ID 由旧版资源初始化清理。"""
    changed_groups = []
    for group in CustomMenuGroup.objects.filter(app=PATCH_APP).order_by("id"):
        menus = group.menus if isinstance(group.menus, list) else []
        reversed_menus, changed = _reverse_menu_nodes(menus)
        if not changed:
            continue
        group.menus = reversed_menus
        changed_groups.append(group)

    if changed_groups:
        CustomMenuGroup.objects.bulk_update(changed_groups, ["menus"], batch_size=100)
    return PatchSettingsSplitMigrationResult(
        roles_updated=0,
        custom_menu_groups_updated=len(changed_groups),
    )


def _migrate_roles(permission_ids: dict[str, int]) -> list[Role]:
    changed_roles = []
    for role in Role.objects.filter(app=PATCH_APP).order_by("id"):
        current_ids = list(role.menu_list or [])
        normalized_ids = {str(menu_id) for menu_id in current_ids}
        migrated_ids = list(current_ids)

        for source_name, target_name in PERMISSION_MAPPING.items():
            if str(permission_ids[source_name]) not in normalized_ids:
                continue
            target_id = permission_ids[target_name]
            if str(target_id) in normalized_ids:
                continue
            migrated_ids.append(target_id)
            normalized_ids.add(str(target_id))

        if migrated_ids != current_ids:
            role.menu_list = migrated_ids
            changed_roles.append(role)

    if changed_roles:
        Role.objects.bulk_update(changed_roles, ["menu_list"], batch_size=100)
    return changed_roles


def _migrate_custom_menu_groups() -> list[CustomMenuGroup]:
    changed_groups = []
    for group in CustomMenuGroup.objects.filter(app=PATCH_APP).order_by("id"):
        menus = group.menus if isinstance(group.menus, list) else []
        migrated_menus, changed = _migrate_menu_nodes(menus)
        if not changed:
            continue
        group.menus = migrated_menus
        changed_groups.append(group)

    if changed_groups:
        CustomMenuGroup.objects.bulk_update(changed_groups, ["menus"], batch_size=100)
    return changed_groups


def _migrate_menu_nodes(nodes: list) -> tuple[list, bool]:
    migrated_nodes = []
    changed = False

    for node in nodes:
        if not isinstance(node, dict):
            migrated_nodes.append(node)
            continue

        node_copy = deepcopy(node)
        if _is_legacy_settings_node(node_copy):
            migrated_nodes.append(_build_settings_parent(node_copy))
            changed = True
            continue

        children = node_copy.get("children")
        if isinstance(children, list):
            migrated_children, children_changed = _migrate_menu_nodes(children)
            if children_changed:
                node_copy["children"] = migrated_children
                changed = True
        migrated_nodes.append(node_copy)

    return migrated_nodes, changed


def _reverse_menu_nodes(nodes: list) -> tuple[list, bool]:
    reversed_nodes = []
    changed = False

    for node in nodes:
        if not isinstance(node, dict):
            reversed_nodes.append(node)
            continue

        node_copy = deepcopy(node)
        if _is_migrated_settings_node(node_copy):
            node_copy["name"] = SOURCE_MENU_NAME
            node_copy["url"] = LEGACY_SETTINGS_URL
            node_copy.pop("children", None)
            reversed_nodes.append(node_copy)
            changed = True
            continue

        children = node_copy.get("children")
        if isinstance(children, list):
            reversed_children, children_changed = _reverse_menu_nodes(children)
            if children_changed:
                node_copy["children"] = reversed_children
                changed = True
        reversed_nodes.append(node_copy)

    return reversed_nodes, changed


def _is_legacy_settings_node(node: dict) -> bool:
    children = node.get("children")
    return node.get("name") == SOURCE_MENU_NAME and _normalize_url(node.get("url")) == LEGACY_SETTINGS_URL and (children is None or children == [])


def _is_migrated_settings_node(node: dict) -> bool:
    if node.get("name") != SETTINGS_PARENT_NAME or _normalize_url(node.get("url")) != LEGACY_SETTINGS_URL:
        return False
    children = node.get("children")
    if not isinstance(children, list):
        return False
    child_names = {child.get("name") for child in children if isinstance(child, dict)}
    return {SOURCE_MENU_NAME, SCAN_MENU_NAME}.issubset(child_names)


def _build_settings_parent(legacy_node: dict) -> dict:
    parent = deepcopy(legacy_node)
    uses_chinese = _uses_chinese_title(parent)
    parent["name"] = SETTINGS_PARENT_NAME
    parent["url"] = LEGACY_SETTINGS_URL
    parent["children"] = [
        {
            "name": SOURCE_MENU_NAME,
            "title": "补丁源" if uses_chinese else "Patch Sources",
            "url": SOURCE_SETTINGS_URL,
        },
        {
            "name": SCAN_MENU_NAME,
            "title": "扫描设置" if uses_chinese else "Scan Settings",
            "url": SCAN_SETTINGS_URL,
        },
    ]
    return parent


def _uses_chinese_title(node: dict) -> bool:
    title = str(node.get("title") or node.get("display_name") or "")
    return any("\u4e00" <= character <= "\u9fff" for character in title)


def _normalize_url(value) -> str:
    url = str(value or "")
    return url.rstrip("/") or "/"

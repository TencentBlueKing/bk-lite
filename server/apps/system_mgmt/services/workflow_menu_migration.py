from copy import deepcopy

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import CustomMenuGroup, Menu, Role

WORKFLOW_APP = "workflow"
BUILTIN_ROLES = {"admin", "normal", "manager"}
GRANT_COPIES = {
    "workflow-View": ("workflow_home-View", "workflow_market-View", "workflow_execution-View"),
    "workflow-Add": ("workflow_market-Add",),
    "workflow-Execute": ("workflow_execution-Execute",),
    "workflow-Approve": ("workflow_execution-Approve",),
}
MENU_NAME_BY_URL = {
    "/workflow/home": "workflow_home",
    "/workflow/workflows": "workflow",
    "/workflow/market": "workflow_market",
    "/workflow/executions": "workflow_execution",
    "/workflow": "workflow_entry",
}


def snapshot_workflow_menu_grants() -> dict[int, set[str]]:
    """在旧的 workflow-Approve 被删掉之前，记下每个角色当前持有的菜单名。"""
    names_by_id = {str(menu_id): name for menu_id, name in Menu.objects.filter(app=WORKFLOW_APP).values_list("id", "name")}
    snapshot = {}
    for role in Role.objects.filter(app=WORKFLOW_APP).order_by("id"):
        snapshot[role.id] = {names_by_id[str(menu_id)] for menu_id in (role.menu_list or []) if str(menu_id) in names_by_id}
    return snapshot


def apply_workflow_menu_permission_split(snapshot: dict[int, set[str]]) -> None:
    """把旧的单一 workflow 授权复制到首页、模版和执行记录。可重复执行。"""
    menu_ids = dict(Menu.objects.filter(app=WORKFLOW_APP).values_list("name", "id"))
    changed_roles = _copy_role_grants(snapshot, menu_ids)
    changed_groups = _migrate_custom_menus()
    if changed_roles or changed_groups:
        logger.info(
            "workflow menu permission split applied roles=%s custom_menus=%s",
            len(changed_roles),
            len(changed_groups),
        )


def _copy_role_grants(snapshot: dict[int, set[str]], menu_ids: dict[str, int]) -> list[Role]:
    changed_roles = []
    for role in Role.objects.filter(app=WORKFLOW_APP, id__in=snapshot).order_by("id"):
        if role.name in BUILTIN_ROLES:
            continue
        granted_names = snapshot.get(role.id, set())
        current_ids = list(role.menu_list or [])
        seen = {str(menu_id) for menu_id in current_ids}
        for source_name, target_names in GRANT_COPIES.items():
            if source_name not in granted_names:
                continue
            for target_name in target_names:
                target_id = menu_ids.get(target_name)
                if target_id is None or str(target_id) in seen:
                    continue
                current_ids.append(target_id)
                seen.add(str(target_id))
        if current_ids != list(role.menu_list or []):
            role.menu_list = current_ids
            changed_roles.append(role)
    if changed_roles:
        Role.objects.bulk_update(changed_roles, ["menu_list"], batch_size=100)
    return changed_roles


def _migrate_custom_menus() -> list[CustomMenuGroup]:
    changed_groups = []
    for group in CustomMenuGroup.objects.filter(app=WORKFLOW_APP).order_by("id"):
        menus = group.menus if isinstance(group.menus, list) else []
        migrated, changed = _migrate_menu_nodes(deepcopy(menus))
        if not changed:
            continue
        group.menus = migrated
        changed_groups.append(group)
    if changed_groups:
        CustomMenuGroup.objects.bulk_update(changed_groups, ["menus"], batch_size=100)
    return changed_groups


def _migrate_menu_nodes(nodes: list) -> tuple[list, bool]:
    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        url = _normalize_url(node.get("url"))
        target_name = MENU_NAME_BY_URL.get(url)
        if target_name and node.get("name") != target_name:
            node["name"] = target_name
            changed = True
        if target_name and node.get("withParentPermission"):
            node.pop("withParentPermission", None)
            changed = True
        children = node.get("children")
        if isinstance(children, list):
            _, children_changed = _migrate_menu_nodes(children)
            changed = changed or children_changed
    return nodes, changed


def _normalize_url(value) -> str:
    url = str(value or "")
    return url.rstrip("/") or "/"

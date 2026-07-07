from copy import deepcopy

from django.core.cache import cache
from django.core.management import BaseCommand
from django.db import transaction

from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.system_mgmt.models import CustomMenuGroup, Group, Menu, Role, User

APP_NAME = "opspilot"
LEGACY_MENU_BASE_NAMES = {
    "knowledge_list",
    "knowledge_document",
    "knowledge_testing",
    "knowledge_setting",
    "knowledge_api",
}
LEGACY_OPERATION_TO_WIKI_OPERATION = {
    "View": "View",
    "Add": "Add",
    "Edit": "Edit",
    "Set": "Edit",
    "Train": "Edit",
    "Delete": "Delete",
}
WIKI_OPERATIONS = ("View", "Add", "Edit", "Delete")
WIKI_MENU_TYPE = "Knowledge Base"
WIKI_MENU_DISPLAY_PREFIX = "Knowledge Base list"
WIKI_MENU_NODE = {
    "name": "wiki_list",
    "display_name": "Knowledge Base",
    "url": "/opspilot/wiki",
    "icon": "zhishiku",
    "children": [
        {
            "name": "wiki_detail",
            "display_name": "Detail",
            "url": "/opspilot/wiki/detail",
            "isNotMenuItem": True,
        }
    ],
}


class Command(BaseCommand):
    help = "Clean OpsPilot legacy knowledge menus and migrate role permissions to Wiki menus"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print pending changes without writing to the database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        legacy_menus = _get_legacy_menus()

        if dry_run:
            role_change_count = _count_roles_with_legacy_menu(legacy_menus)
            custom_group_change_count = _count_custom_groups_with_legacy_menu(legacy_menus)
            self.stdout.write(self.style.WARNING("DRY-RUN: no database changes will be written."))
            self.stdout.write(f"legacy menus to delete: {len(legacy_menus)}")
            self.stdout.write(f"roles to update: {role_change_count}")
            self.stdout.write(f"custom menu groups to update: {custom_group_change_count}")
            return

        with transaction.atomic():
            wiki_menu_ids = _ensure_wiki_menus()
            changed_role_ids = _migrate_roles(legacy_menus, wiki_menu_ids)
            changed_group_count = _migrate_custom_menu_groups(legacy_menus)
            deleted_menu_count, _ = Menu.objects.filter(id__in=[menu.id for menu in legacy_menus]).delete()

        _clear_menu_cache()
        _clear_permission_cache_for_roles(changed_role_ids)

        self.stdout.write(self.style.SUCCESS("OpsPilot legacy knowledge menus cleanup completed."))
        self.stdout.write(f"legacy menus deleted: {deleted_menu_count}")
        self.stdout.write(f"roles updated: {len(changed_role_ids)}")
        self.stdout.write(f"custom menu groups updated: {changed_group_count}")


def _get_legacy_menus():
    return [menu for menu in Menu.objects.filter(app=APP_NAME).order_by("id") if _is_legacy_permission_name(menu.name)]


def _is_legacy_permission_name(name):
    base_name, operation = _split_permission_name(name)
    return base_name in LEGACY_MENU_BASE_NAMES and operation in LEGACY_OPERATION_TO_WIKI_OPERATION


def _split_permission_name(name):
    if "-" not in name:
        return name, ""
    return name.rsplit("-", 1)


def _count_roles_with_legacy_menu(legacy_menus):
    legacy_ids = {str(menu.id) for menu in legacy_menus}
    count = 0
    for role in Role.objects.all().only("menu_list"):
        if any(str(menu_id) in legacy_ids for menu_id in role.menu_list):
            count += 1
    return count


def _count_custom_groups_with_legacy_menu(legacy_menus):
    legacy_ids = {str(menu.id) for menu in legacy_menus}
    count = 0
    for group in CustomMenuGroup.objects.filter(app=APP_NAME).only("menus"):
        _, has_changes = _clean_menu_nodes(group.menus if isinstance(group.menus, list) else [], legacy_ids)
        if has_changes:
            count += 1
    return count


def _ensure_wiki_menus():
    existing_menus = {menu.name: menu for menu in Menu.objects.filter(app=APP_NAME, name__startswith="wiki_list-")}
    create_menus = []
    update_menus = []

    for order, operation in enumerate(WIKI_OPERATIONS, start=1):
        name = f"wiki_list-{operation}"
        display_name = f"{WIKI_MENU_DISPLAY_PREFIX}-{operation}"
        menu = existing_menus.get(name)
        if menu is None:
            create_menus.append(
                Menu(
                    name=name,
                    display_name=display_name,
                    order=order,
                    app=APP_NAME,
                    menu_type=WIKI_MENU_TYPE,
                )
            )
            continue

        changed = False
        for field, value in {"display_name": display_name, "order": order, "menu_type": WIKI_MENU_TYPE}.items():
            if getattr(menu, field) != value:
                setattr(menu, field, value)
                changed = True
        if changed:
            update_menus.append(menu)

    if create_menus:
        Menu.objects.bulk_create(create_menus, batch_size=100)
    if update_menus:
        Menu.objects.bulk_update(update_menus, ["display_name", "order", "menu_type"], batch_size=100)

    return dict(Menu.objects.filter(app=APP_NAME, name__startswith="wiki_list-").values_list("name", "id"))


def _migrate_roles(legacy_menus, wiki_menu_ids):
    legacy_menu_by_id = {str(menu.id): menu for menu in legacy_menus}
    changed_roles = []

    for role in Role.objects.all().order_by("id"):
        new_menu_list, changed = _migrate_role_menu_list(role, legacy_menu_by_id, wiki_menu_ids)
        if changed:
            role.menu_list = new_menu_list
            changed_roles.append(role)

    if changed_roles:
        Role.objects.bulk_update(changed_roles, ["menu_list"], batch_size=100)

    return [role.id for role in changed_roles]


def _migrate_role_menu_list(role, legacy_menu_by_id, wiki_menu_ids):
    kept_menu_ids = []
    mapped_wiki_ids = []
    changed = False

    for menu_id in role.menu_list:
        legacy_menu = legacy_menu_by_id.get(str(menu_id))
        if legacy_menu is None:
            kept_menu_ids.append(menu_id)
            continue

        changed = True
        if role.app == APP_NAME:
            wiki_menu_id = _get_mapped_wiki_menu_id(legacy_menu.name, wiki_menu_ids)
            if wiki_menu_id is not None:
                mapped_wiki_ids.append(wiki_menu_id)

    return _deduplicate_menu_ids([*kept_menu_ids, *mapped_wiki_ids]), changed


def _get_mapped_wiki_menu_id(legacy_name, wiki_menu_ids):
    _, legacy_operation = _split_permission_name(legacy_name)
    wiki_operation = LEGACY_OPERATION_TO_WIKI_OPERATION.get(legacy_operation)
    if not wiki_operation:
        return None
    return wiki_menu_ids.get(f"wiki_list-{wiki_operation}")


def _deduplicate_menu_ids(menu_ids):
    result = []
    seen = set()
    for menu_id in menu_ids:
        key = str(menu_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(menu_id)
    return result


def _migrate_custom_menu_groups(legacy_menus):
    legacy_ids = {str(menu.id) for menu in legacy_menus}
    changed_groups = []

    for group in CustomMenuGroup.objects.filter(app=APP_NAME).order_by("id"):
        menus = group.menus if isinstance(group.menus, list) else []
        cleaned_menus, has_changes = _clean_menu_nodes(menus, legacy_ids)
        if has_changes and not _has_wiki_menu(cleaned_menus):
            cleaned_menus.append(deepcopy(WIKI_MENU_NODE))
        if has_changes:
            group.menus = cleaned_menus
            changed_groups.append(group)

    if changed_groups:
        CustomMenuGroup.objects.bulk_update(changed_groups, ["menus"], batch_size=100)

    return len(changed_groups)


def _clean_menu_nodes(nodes, legacy_ids):
    cleaned_nodes = []
    has_changes = False

    for node in nodes:
        if not isinstance(node, dict):
            cleaned_nodes.append(node)
            continue

        node_copy = deepcopy(node)
        children = node_copy.get("children")
        if isinstance(children, list):
            node_copy["children"], child_changed = _clean_menu_nodes(children, legacy_ids)
            has_changes = has_changes or child_changed

        if _is_legacy_custom_menu_node(node_copy, legacy_ids):
            has_changes = True
            continue

        cleaned_nodes.append(node_copy)

    return cleaned_nodes, has_changes


def _is_legacy_custom_menu_node(node, legacy_ids):
    menu_id = node.get("menu_id")
    if menu_id is not None and str(menu_id) in legacy_ids:
        return True

    for key in ("name", "id"):
        value = node.get(key)
        if isinstance(value, str) and _is_legacy_menu_node_name(value):
            return True

    url = node.get("url")
    return isinstance(url, str) and url.startswith("/opspilot/knowledge")


def _is_legacy_menu_node_name(name):
    if name in LEGACY_MENU_BASE_NAMES:
        return True
    return _is_legacy_permission_name(name)


def _has_wiki_menu(nodes):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("name") == "wiki_list" or node.get("id") == "wiki_list":
            return True
        url = node.get("url")
        if isinstance(url, str) and url.startswith("/opspilot/wiki"):
            return True
        if _has_wiki_menu(node.get("children") or []):
            return True
    return False


def _clear_menu_cache():
    if hasattr(cache, "delete_pattern"):
        cache.delete_pattern("menus-user:*")
        return

    cache.delete_many([f"menus-user:{user_id}" for user_id in User.objects.values_list("id", flat=True)])


def _clear_permission_cache_for_roles(role_ids):
    if not role_ids:
        return

    role_id_set = set(role_ids)
    group_ids = set(Group.objects.filter(roles__id__in=role_ids).values_list("id", flat=True))
    affected_users = []

    for user in User.objects.all().only("username", "domain", "role_list", "group_list"):
        user_role_ids = set(user.role_list or [])
        user_group_ids = set(user.group_list or [])
        if role_id_set.intersection(user_role_ids) or group_ids.intersection(user_group_ids):
            affected_users.append({"username": user.username, "domain": user.domain})

    if affected_users:
        clear_users_permission_cache(affected_users)

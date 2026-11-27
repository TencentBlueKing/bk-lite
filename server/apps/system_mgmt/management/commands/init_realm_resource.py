import json
import os
from copy import deepcopy

from django.core.management import BaseCommand
from django.db import transaction

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.module_scope import EXCLUDED_CLIENTS, MODULE_ADMIN_ROLE, MODULE_AUDITOR_ROLE
from apps.core.utils.permission_cache import clear_all_permission_cache
from apps.system_mgmt.management.commands._install_apps import get_install_apps
from apps.system_mgmt.models import App, Group, Menu, Role, User
from apps.system_mgmt.services.cmdb_asset_export_permission import grant_asset_export_from_view, prepare_asset_export_grant
from apps.system_mgmt.services.platform_roles import is_view_menu
from apps.system_mgmt.services.workflow_menu_migration import apply_workflow_menu_permission_split, snapshot_workflow_menu_grants
from apps.system_mgmt.utils.group_utils import GroupUtils


class Command(BaseCommand):
    help = "初始化Realm资源数据"

    def handle(self, *args, **options):
        # Resolve install_apps before the file-read loop so EnterpriseFootprintError
        # propagates immediately instead of being swallowed by the per-file try/except.
        install_apps = get_install_apps()
        menu_dir = "support-files/system_mgmt/menus"
        MENUS = []
        for root, dirs, files in os.walk(menu_dir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            menu_data = json.load(f)
                            menu_data = extend_menus_by_install_apps(menu_data, install_apps)
                            MENUS.append(menu_data)
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {e}")

        print(f"Read {len(MENUS)} menu files")
        with transaction.atomic():
            permission_signature_before = _permission_signature()
            for app_obj in MENUS:
                app_inst, _ = App.objects.update_or_create(
                    name=app_obj["client_id"],
                    defaults={
                        "display_name": app_obj["name"],
                        "description": app_obj["description"],
                        "is_build_in": True,
                        "url": app_obj["url"],
                        "icon": app_obj.get("icon", app_obj["client_id"]),
                        "tags": app_obj.get("tags", []),
                    },
                )
                print(f"create {app_obj['client_id']} success")
                grant_snapshot = snapshot_workflow_menu_grants() if app_obj["client_id"] == "workflow" else None
                export_grant = prepare_asset_export_grant() if app_obj["client_id"] == "cmdb" else None
                create_resource(app_inst, app_obj["menus"])
                if grant_snapshot is not None:
                    apply_workflow_menu_permission_split(grant_snapshot)
                print(f"create {app_obj['client_id']} resource success")
                create_default_roles(app_inst, app_obj["roles"])
                if export_grant is not None:
                    grant_asset_export_from_view(export_grant)
                print(f"create {app_obj['client_id']} roles success")
            if GroupUtils.builtin_root() is None:
                Group.objects.get_or_create(
                    name="Default",
                    parent_id=0,
                    defaults={"description": "Default group", "is_builtin": True},
                )
            Group.objects.get_or_create(name="Guest", parent_id=0, defaults={"description": "Guest group"})
            from apps.system_mgmt.services.platform_roles import ensure_platform_auditor_role

            ensure_platform_auditor_role()
            if _permission_signature() != permission_signature_before:
                clear_all_permission_cache()
            from apps.system_mgmt.services.credential_service import seed_builtin_types

            seed_builtin_types()


def _permission_signature():
    """返回会影响鉴权结果的菜单/角色签名，避免 no-op 启动全量打冷缓存。"""
    menus = tuple(Menu.objects.order_by("id").values_list("id", "app", "name"))
    roles = tuple(
        (role.id, role.app, role.name, tuple(role.menu_list or [])) for role in Role.objects.order_by("id").only("id", "app", "name", "menu_list")
    )
    return menus, roles


def extend_menus_by_install_apps(menu_data: dict, install_apps: set[str]) -> dict:
    result = deepcopy(menu_data)
    if result.get("client_id") != "system-manager" or "license_mgmt" not in install_apps:
        return result

    security_menu = next((item for item in result.get("menus", []) if item.get("name") == "Security"), None)
    setting_menu = next((item for item in result.get("menus", []) if item.get("name") == "Setting"), None)
    if not security_menu or not setting_menu:
        return result

    setting_children = setting_menu.setdefault("children", [])
    if any(child.get("id") == "license_mgmt" for child in setting_children):
        return result

    setting_children.append({"id": "portal_settings", "name": "Portal Settings", "operation": ["View", "Edit"]})
    setting_children.append({"id": "license_mgmt", "name": "License Management", "operation": ["View", "Add", "Edit", "Delete"]})

    security_children = security_menu.setdefault("children", [])
    sensitive_info = {"id": "sensitive_info", "name": "Sensitive Info", "operation": ["View", "Edit", "Add", "Delete"]}
    after_index = next((index for index, child in enumerate(security_children) if child.get("id") == "super_admin"), None)
    if after_index is None:
        security_children.append(sensitive_info)
    else:
        security_children.insert(after_index + 1, sensitive_info)

    security_role = next((item for item in result.get("roles", []) if item.get("name") == "security"), None)
    if security_role:
        security_role_menus = security_role.setdefault("menus", [])
        for menu_name in ("sensitive_info-View", "sensitive_info-Add", "sensitive_info-Edit", "sensitive_info-Delete"):
            if menu_name not in security_role_menus:
                security_role_menus.append(menu_name)

    return result


def create_resource(app_inst: App, menus):
    index = 1
    create_menu_list = []
    update_menu_list = []
    exist_menus = Menu.objects.filter(app=app_inst.name)
    delete_menus = []
    menu_map = {i.name: i for i in exist_menus}
    for i in menus:
        for child in i["children"]:
            for operate in child["operation"]:
                name = f"{child['id']}-{operate}"
                if name in menu_map:
                    update_obj = menu_map[name]
                    update_obj.display_name = f"{child['name']}-{operate}"
                    update_obj.order = index
                    update_obj.menu_type = i["name"]
                    update_menu_list.append(update_obj)
                    menu_map.pop(name)
                else:
                    create_menu_list.append(
                        Menu(
                            name=f"{child['id']}-{operate}",
                            display_name=f"{child['name']}-{operate}",
                            order=index,
                            menu_type=i["name"],
                            app=app_inst.name,
                        )
                    )
                index += 1
    for i in menu_map.values():
        delete_menus.append(i.id)
    Menu.objects.filter(id__in=delete_menus).delete()
    role_list = list(Role.objects.all())
    for i in role_list:
        if set(i.menu_list).intersection(set(delete_menus)):
            i.menu_list = [j for j in i.menu_list if j not in delete_menus]
    Role.objects.bulk_update(role_list, ["menu_list"], batch_size=100)
    Menu.objects.bulk_create(create_menu_list, batch_size=100)
    Menu.objects.bulk_update(update_menu_list, ["display_name", "order", "menu_type"], batch_size=100)


def create_default_roles(app_inst: App, roles):
    menus = Menu.objects.filter(app=app_inst.name).values("id", "name")
    exist_roles = Role.objects.filter(app=app_inst.name)
    role_map = {i.name: i for i in exist_roles}
    add_roles = []
    update_roles = []
    for i in roles:
        is_update = i["name"] in role_map
        if i["name"] in role_map:
            role_obj = role_map[i["name"]]
        else:
            role_obj = Role(name=i["name"], app=app_inst.name)
        menu_ids = [u["id"] for u in menus if u["name"] in i["menus"]]
        role_obj.menu_list = menu_ids
        if is_update:
            update_roles.append(role_obj)
        else:
            add_roles.append(role_obj)
    if "manager" not in role_map:
        add_roles.append(Role(name="manager", app=app_inst.name, menu_list=[i["id"] for i in menus]))
    else:
        role_obj = role_map["manager"]
        role_obj.menu_list = [i["id"] for i in menus]
        update_roles.append(role_obj)

    if app_inst.name in EXCLUDED_CLIENTS:
        Role.objects.bulk_create(add_roles, batch_size=100)
        Role.objects.bulk_update(update_roles, ["menu_list"], batch_size=100)
        remove_module_builtin_roles(app_inst.name)
        return

    menu_rows = list(menus)
    module_specs = (
        (MODULE_ADMIN_ROLE, [row["id"] for row in menu_rows]),
        (MODULE_AUDITOR_ROLE, [row["id"] for row in menu_rows if is_view_menu(row["name"])]),
    )
    for role_name, menu_ids in module_specs:
        if role_name in role_map:
            role_obj = role_map[role_name]
            role_obj.menu_list = menu_ids
            update_roles.append(role_obj)
        else:
            add_roles.append(Role(name=role_name, app=app_inst.name, menu_list=menu_ids))

    Role.objects.bulk_create(add_roles, batch_size=100)
    Role.objects.bulk_update(update_roles, ["menu_list"], batch_size=100)


def remove_module_builtin_roles(app_name: str):
    """去掉不该存在的模块角色，并把已经配到人身上的 id 摘掉。"""
    role_ids = set(Role.objects.filter(app=app_name, name__in=(MODULE_ADMIN_ROLE, MODULE_AUDITOR_ROLE)).values_list("id", flat=True))
    if not role_ids:
        return
    changed_users = []
    for user in User.objects.all().only("id", "role_list"):
        current = list(user.role_list or [])
        kept = [item for item in current if item not in role_ids]
        if kept != current:
            user.role_list = kept
            changed_users.append(user)
    if changed_users:
        User.objects.bulk_update(changed_users, ["role_list"])
    Role.objects.filter(id__in=role_ids).delete()


def get_all_clients(client):
    res = client.realm_client.get_clients()
    return_data = {i["clientId"]: {"id": i["id"], "name": i["name"]} for i in res}
    return return_data

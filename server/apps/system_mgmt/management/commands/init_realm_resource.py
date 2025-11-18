import json
import logging
import os

from django.core.management import BaseCommand

from apps.system_mgmt.models import App, Group, Menu, Role

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "初始化Realm资源数据"

    def handle(self, *args, **options):
        menu_dir = "support-files/system_mgmt/menus"
        MENUS = []
        for root, dirs, files in os.walk(menu_dir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            menu_data = json.load(f)
                            MENUS.append(menu_data)
                    except Exception as e:
                        logger.error(f"Error reading {file_path}: {e}")

        print(f"Read {len(MENUS)} menu files")
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
            create_resource(app_inst, app_obj["menus"])
            print(f"create {app_obj['client_id']} resource success")
            create_default_roles(app_inst, app_obj["roles"])
            print(f"create {app_obj['client_id']} roles success")
        Group.objects.get_or_create(name="Default", parent_id=0, defaults={"description": "Default group"})
        Group.objects.get_or_create(name="Guest", parent_id=0, defaults={"description": "Guest group"})


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
    Menu.objects.bulk_update(update_menu_list, ["display_name", "order"], batch_size=100)


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

    Role.objects.bulk_create(add_roles, batch_size=100)
    Role.objects.bulk_update(update_roles, ["menu_list"], batch_size=100)


def get_all_clients(client):
    res = client.realm_client.get_clients()
    return_data = {i["clientId"]: {"id": i["id"], "name": i["name"]} for i in res}
    return return_data

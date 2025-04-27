import json
import logging
import os

from django.core.management import BaseCommand

from apps.system_mgmt.utils.keycloak_client import KeyCloakClient

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "初始化Realm资源数据"

    def handle(self, *args, **options):
        keycloak_client = KeyCloakClient()
        menu_dir = "support-files/keycloak/menus"
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
            payload = {
                "clientId": app_obj["client_id"],
                "name": app_obj["name"],
                "description": app_obj["description"],
                "baseUrl": app_obj["url"],
                "serviceAccountsEnabled": True,
                "directAccessGrantsEnabled": True,
                "authorizationServicesEnabled": True,
            }
            client_id = keycloak_client.realm_client.create_client(payload, True)
            print(f"create {app_obj['client_id']} success")
            resource = keycloak_client.realm_client.get_client_authz_resources(client_id)
            default_resource = [i for i in resource if i["name"] == "Default Resource"]
            if default_resource:
                keycloak_client.realm_client.delete_client_authz_resource(client_id, default_resource[0]["_id"])
            create_resource(client_id, app_obj["menus"], keycloak_client)
            print(f"create {app_obj['client_id']} resource success")
            create_default_roles(client_id, keycloak_client, app_obj["roles"])
            print(f"create {app_obj['client_id']} roles success")


def create_resource(client_id, menus, client):
    index = 1
    for i in menus:
        for child in i["children"]:
            for operate in child["operation"]:
                payload = {
                    "type": i["name"],
                    "name": f"{child['id']}-{operate}",
                    "displayName": f"{child['name']}-{operate}",
                    "attributes": {"index": index},
                }
                index += 1
                client.realm_client.create_client_authz_resource(client_id, payload, True)


def create_default_roles(client_id, client, roles):
    all_resource = client.realm_client.get_client_authz_resources(client_id)
    policies = client.realm_client.get_client_authz_policies(client_id)
    policy_map = {i["name"]: i["id"] for i in policies if i["type"] == "role"}
    for i in roles:
        client.realm_client.create_realm_role({"name": i["role_name"]}, True)
        role_info = client.realm_client.get_realm_role(role_name=i["role_name"])
        if i["name"] in policy_map:
            policy_id = policy_map[i["name"]]
        else:
            policy_data = {
                "type": "role",
                "logic": "POSITIVE",
                "decisionStrategy": "AFFIRMATIVE",
                "name": i["name"],
                "roles": [{"id": role_info["id"]}],
            }
            policy_obj = client.realm_client.create_client_authz_role_based_policy(client_id, policy_data, True)
            policy_id = policy_obj["id"]
        if not i["menus"]:
            continue
        menu_ids = [u["_id"] for u in all_resource if u["name"] in i["menus"]]
        try:
            client.create_permission(client_id, menu_ids, i["name"], policy_id)
        except Exception as e:
            logger.error(e)


def get_all_clients(client):
    res = client.realm_client.get_clients()
    return_data = {i["clientId"]: {"id": i["id"], "name": i["name"]} for i in res}
    return return_data

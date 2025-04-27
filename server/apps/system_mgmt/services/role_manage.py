import json
from collections import defaultdict

from keycloak import KeycloakGetError, urls_patterns
from keycloak.exceptions import raise_error_from_response

from apps.core.backends import cache
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.utils.db_utils import SQLExecute
from apps.system_mgmt.utils.keycloak_client import KeyCloakClient


class RoleManage(object):
    def __init__(self):
        self.keycloak_client = KeyCloakClient()

    def get_role_list(self, client_ids):
        """角色列表"""
        policies = []
        for client_id in client_ids:
            policies.extend(self.keycloak_client.realm_client.get_client_authz_policies(client_id))
        all_roles = self.keycloak_client.get_realm_roles()
        role_map = {i["id"]: i["name"] for i in all_roles}
        roles = [
            {
                "policy_id": i["id"],
                "display_name": i["name"],
                "role_id": json.loads(i["config"]["roles"])[0]["id"],
                "role_name": role_map.get(json.loads(i["config"]["roles"])[0]["id"], ""),
            }
            for i in policies
            if i["type"] == "role"
        ]
        return roles

    def get_role_tree(self, client_list):
        all_roles = self.keycloak_client.get_realm_roles()
        role_map = {i["id"]: i["name"] for i in all_roles}
        return_data = []
        for client_obj in client_list:
            policies = self.keycloak_client.realm_client.get_client_authz_policies(client_obj["id"])
            roles = [
                {
                    "policy_id": i["id"],
                    "display_name": i["name"],
                    "role_id": json.loads(i["config"]["roles"])[0]["id"],
                    "role_name": role_map.get(json.loads(i["config"]["roles"])[0]["id"], ""),
                }
                for i in policies
                if i["type"] == "role"
            ]
            return_data.append({"id": client_obj["id"], "display_name": client_obj["name"], "children": roles})
        return return_data

    def role_users(self, query, role_id):
        """获取角色关联的用户"""
        result = self.keycloak_client.get_role_users(role_id, query)
        return result

    def get_all_menus(self, client_id, user_menus=None, username="", is_superuser=False):
        cache_key = f"all_menus_{client_id}"
        if user_menus is not None:
            user_menus.sort()
            cache_key = f"all_menus_{client_id}_{username}"
        all_menus = cache.get(cache_key)
        if not all_menus:
            if not is_superuser and not user_menus:
                menus = []
            else:
                menus = self.keycloak_client.realm_client.get_client_authz_resources(client_id)
                if user_menus:
                    menus = [i for i in menus if i["name"] in user_menus]
            all_menus = self.transform_data(menus)
            cache.set(cache_key, all_menus, 60 * 30)
        return all_menus

    def get_policy_by_by_roles(self, client_id, roles):
        policies = self.keycloak_client.realm_client.get_client_authz_policies(client_id)
        all_roles = self.keycloak_client.get_realm_roles()
        role_map = {i["name"]: i["id"] for i in all_roles}
        user_roles = [role_map.get(i) for i in roles]
        user_policies = []
        for i in policies:
            role_obj = json.loads(i["config"].get("roles", "[]"))
            if not role_obj or i["type"] != "role":
                continue
            role_obj = role_obj[0]
            if role_obj["id"] in user_roles:
                user_policies.append(i["id"])
        return user_policies

    @staticmethod
    def transform_data(data):
        if not data:
            return []
        data = [
            {
                "name": i["name"],
                "type": i["type"],
                "display_name": i["displayName"],
                "index": int(i["attributes"]["index"][0]),
            }
            for i in data
            if i.get("attributes", {}).get("index") is not None
        ]
        data.sort(key=lambda i: i["index"])
        transformed = defaultdict(lambda: defaultdict(lambda: {"display_name": "", "operation": []}))
        for item in data:
            type_ = item["type"]
            name_operation = item["name"].split("-")
            name = name_operation[0]
            operation = name_operation[1] if len(name_operation) > 1 else ""
            display_name = " ".join(item["display_name"].split("-")[:-1])

            if transformed[type_][name]["display_name"] == "":
                transformed[type_][name]["display_name"] = display_name

            transformed[type_][name]["operation"].append(operation)

        result = []
        for type_, names in transformed.items():
            children = []
            for name, details in names.items():
                children.append(
                    {
                        "name": name,
                        "display_name": details["display_name"],
                        "operation": details["operation"],
                    }
                )
            result.append({"name": type_, "display_name": type_, "children": children})

        return result

    def role_menus(self, client_id, policy_id):
        """获取角色权限"""
        client = SupplementApi(self.keycloak_client.realm_client.connection)
        select_menus = []
        permissions = client.get_permission_by_policy_id(client_id, policy_id)

        if permissions:
            resources = client.get_resources(client_id, permissions[0]["id"])
            select_menus = [i["name"] for i in resources]
        return select_menus

    def role_create(self, data):
        """创建角色，先创建角色再创建角色对应的策略"""
        role_name = data["name"]
        client_name = data.pop("client_id")
        client_id = data.pop("id")
        data.pop("superior_role", "")
        role_params = {"name": f"{client_name}_{role_name}"}
        self.keycloak_client.realm_client.create_realm_role(role_params, True)
        role_info = self.keycloak_client.realm_client.get_realm_role(role_name=f"{client_name}_{role_name}")
        policy_data = {
            "type": "role",
            "logic": "POSITIVE",
            "decisionStrategy": "AFFIRMATIVE",
            "name": role_name,
            "roles": [{"id": role_info["id"]}],
        }
        policy_obj = self.keycloak_client.realm_client.create_client_authz_role_based_policy(
            client_id, policy_data, True
        )
        return {
            "policy_id": policy_obj["id"],
            "display_name": role_name,
            "role_name": role_info["name"],
            "role_id": role_info["id"],
        }

    def role_delete(self, client_id, policy_id, policy_name, role_name):
        """
        删除角色
        1.角色关联校验（校验角色是否被用户或者组织关联）
        2.移除角色绑定的权限
        3.删除角色
        """

        # 禁止删除内置角色

        if policy_name in ["admin", "normal"]:
            raise Exception("内置角色禁止删除！")
        # 角色关联校验（校验角色是否被用户或者组织关联）
        groups = self.keycloak_client.realm_client.get_realm_role_groups(role_name)
        if groups:
            msg = "、".join([i["name"] for i in groups])
            raise Exception(f"角色已被下列组织使用：{msg}！")

        users = self.keycloak_client.realm_client.get_realm_role_members(role_name)
        if users:
            msg = "、".join([i["username"] for i in users])
            raise Exception(f"角色已被下列用户使用：{msg}！")
        # 移除角色权限
        supplement_api = SupplementApi(self.keycloak_client.realm_client.connection)
        permissions = supplement_api.get_permission_by_policy_id(client_id, policy_id)
        for permission_info in permissions:
            supplement_api.delete_permission(client_id, permission_info["id"])
        # 删除角色
        self.keycloak_client.realm_client.delete_realm_role(role_name)
        self.keycloak_client.realm_client.delete_client_authz_policy(client_id, policy_id)

    def role_update(self, client_id, policy_id, policy_name, role_id):
        """修改角色信息"""
        supplement_api = SupplementApi(self.keycloak_client.realm_client.connection)
        supplement_api.update_policy(client_id, policy_id, policy_name, role_id)

    def role_set_permissions(self, data, role_name):
        """设置角色权限"""
        if role_name == "admin":
            raise BaseAppException("超管角色拥有全部权限，无需设置！")
        client_id = self.keycloak_client.get_client_id()
        all_resources = self.keycloak_client.realm_client.get_client_authz_resources(client_id)
        resource_mapping = {i["name"]: i["_id"] for i in all_resources}
        # 获取角色映射的policy_id（角色与policy一对一映射）
        policies = self.keycloak_client.realm_client.get_client_authz_policies(client_id)
        policy_id = None
        for policy in policies:
            # 取角色的policy_id
            if policy["name"] == role_name:
                policy_id = policy["id"]
                break
        permission_name_set = set(data)
        # 判断是否需要初始化权限，若需要就进行资源与权限的初始化
        all_permissions = self.keycloak_client.realm_client.get_client_authz_permissions(client_id)
        need_init_permissions = permission_name_set - {i["name"] for i in all_permissions}
        for permission_name in need_init_permissions:
            resource_id = resource_mapping.get(permission_name)
            if not resource_id:
                resource = {
                    "name": permission_name,
                    "displayName": "",
                    "type": "",
                    "icon_uri": "",
                    "scopes": [],
                    "ownerManagedAccess": False,
                    "attributes": {},
                }
                resource_resp = self.keycloak_client.realm_client.create_client_authz_resource(
                    client_id, resource, True
                )
                resource_id = resource_resp["_id"]
            permission = {
                "resources": [resource_id],
                "policies": [],
                "name": permission_name,
                "description": "",
                "decisionStrategy": "AFFIRMATIVE",
                "resourceType": "",
            }
            self.keycloak_client.realm_client.create_client_authz_resource_based_permission(client_id, permission, True)

        # 判断权限是否需要更新
        all_permissions = self.keycloak_client.realm_client.get_client_authz_permissions(client_id)
        supplement_api = SupplementApi(self.keycloak_client.realm_client.connection)
        for permission_info in all_permissions:
            permission_policies = supplement_api.get_policies_by_permission_id(client_id, permission_info["id"])
            permission_policy_ids = [i["id"] for i in permission_policies]
            # 需要绑定权限与角色的
            if permission_info["name"] in permission_name_set:
                if policy_id in permission_policy_ids:
                    continue
                permission_policy_ids.append(policy_id)
            # 需求解绑权限与角色的
            else:
                # 当前角色解除权限绑定
                if policy_id not in permission_policy_ids:
                    continue
                permission_policy_ids.remove(policy_id)
            # 执行权限更新
            permission_info.update(policies=permission_policy_ids)
            supplement_api.update_permission(client_id, permission_info["id"], permission_info)

    def role_add_user(self, role_id, user_ids):
        """为某个用户设置一个角色"""
        role = self.keycloak_client.realm_client.get_realm_role_by_id(role_id)
        for user_id in user_ids:
            self.keycloak_client.realm_client.assign_realm_roles(user_id, role)

    def role_remove_user(self, role_id, user_ids):
        """移除角色下的某个用户"""
        role = self.keycloak_client.realm_client.get_realm_role_by_id(role_id)
        for user_id in user_ids:
            self.keycloak_client.realm_client.delete_realm_roles_of_user(user_id, role)

    def role_add_groups(self, data, role_id):
        """为一些组添加某个角色"""
        role = self.keycloak_client.realm_client.get_realm_role_by_id(role_id)
        for group_id in data:
            self.keycloak_client.realm_client.assign_group_realm_roles(group_id, role)

    def role_remove_groups(self, data, role_id):
        """将一些组移除某个角色"""
        role = self.keycloak_client.realm_client.get_realm_role_by_id(role_id)

        for group_id in data:
            self.keycloak_client.realm_client.delete_group_realm_roles(group_id, role)

    def role_groups(self, role_name):
        """获取角色关联的组"""
        result = self.keycloak_client.realm_client.get_realm_role_groups(role_name)
        return result

    def set_role_menus(self, policy_id, menus, policy_name, client_id):
        supplement_api = SupplementApi(self.keycloak_client.realm_client.connection)
        permissions = supplement_api.get_permission_by_policy_id(client_id, policy_id)
        for permission_info in permissions:
            supplement_api.delete_permission(client_id, permission_info["id"])
        menu_ids = self.format_menus(menus, client_id)
        self.keycloak_client.create_permission(client_id, menu_ids, policy_name, policy_id)
        cache_key = f"all_menus_{client_id}"
        keys = self.get_cache_keys(cache_key)
        cache.delete_many(keys)

    @staticmethod
    def get_cache_keys(cache_key):
        sql = "select * from django_cache where cache_key like %(key)s"
        data = SQLExecute.execute_sql(sql, {"key": f"%{cache_key}%"}, db_name="system_mgmt")
        return [i["cache_key"].split(":", 3)[-1] for i in data]

    def format_menus(self, menus, client_id):
        all_menus = self.keycloak_client.realm_client.get_client_authz_resources(client_id)
        menu_ids = [i["_id"] for i in all_menus if i["name"] in menus]
        return menu_ids


class SupplementApi(object):
    def __init__(self, connection):
        self.connection = connection

    def get_permission_by_policy_id(self, client_id, policy_id):
        """根据策略查询权限"""
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ_POLICY + "/dependentPolicies"
        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "policy-id": policy_id,
        }
        data_raw = self.connection.raw_get(url.format(**params_path))
        return raise_error_from_response(data_raw, KeycloakGetError)

    def update_permission(self, client_id, permission_id, permission):
        """设置权限"""
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ + "/permission/resource/{permission_id}"
        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "permission_id": permission_id,
        }
        data_raw = self.connection.raw_put(url.format(**params_path), json.dumps(permission))
        return raise_error_from_response(data_raw, KeycloakGetError)

    def update_policy(self, client_id, policy_id, policy_name, role_id):
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ + "/policy/role/{policy_id}"

        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "policy_id": policy_id,
        }
        params = {
            "type": "role",
            "logic": "POSITIVE",
            "decisionStrategy": "AFFIRMATIVE",
            "name": policy_name,
            "roles": [{"id": role_id}],
        }
        data_raw = self.connection.raw_put(url.format(**params_path), json.dumps(params))
        return raise_error_from_response(data_raw, KeycloakGetError)

    def delete_permission(self, client_id, permission_id):
        """设置权限"""
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ + "/permission/resource/{permission_id}"
        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "permission_id": permission_id,
        }
        data_raw = self.connection.raw_delete(url.format(**params_path))
        return raise_error_from_response(data_raw, KeycloakGetError)

    def get_policies_by_permission_id(self, client_id, permission_id):
        """根据权限ID查询策略"""
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ + "/policy/{permission_id}/associatedPolicies"
        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "permission_id": permission_id,
        }
        data_raw = self.connection.raw_get(url.format(**params_path))
        return raise_error_from_response(data_raw, KeycloakGetError)

    def get_resources(self, client_id, policy_id):
        """获取资源"""
        url = urls_patterns.URL_ADMIN_CLIENT_AUTHZ_POLICY + "/resources"
        params_path = {
            "realm-name": self.connection.realm_name,
            "id": client_id,
            "policy-id": policy_id,
        }
        data_raw = self.connection.raw_get(url.format(**params_path))
        return raise_error_from_response(data_raw, KeycloakGetError)

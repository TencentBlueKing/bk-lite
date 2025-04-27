import json

from apps.core.backends import cache
from apps.system_mgmt.models import UserRule
from apps.system_mgmt.services.role_manage import RoleManage
from apps.system_mgmt.utils.keycloak_client import KeyCloakClient


class UserManage(object):
    def __init__(self):
        self.keycloak_client = KeyCloakClient()

    @staticmethod
    def get_first_and_max(params):
        """格式化page参数, 获取first与max"""
        page, page_size = int(params.get("page", 1)), int(params.get("page_size", 20))
        _first = (page - 1) * page_size
        _max = page_size
        return _first, _max

    def group_retrieve(self, group_id):
        """查询某个组织的信息"""
        group = self.keycloak_client.realm_client.get_group(group_id)
        return group

    def user_list(self, query_params, group_id=None):
        """用户列表"""
        if group_id:
            # users = self.keycloak_client.realm_client.get_group_members(group_id, query_params)
            users = self.keycloak_client.get_group_users(group_id, query_params)
            user_count = self.keycloak_client.get_group_user_count(group_id, query_params["search"])
        else:
            users = self.keycloak_client.realm_client.get_users(query_params)
            user_count = self.keycloak_client.realm_client.users_count(query_params)
        return {"count": user_count, "users": users}

    def user_all(self):
        """获取所有用户"""
        users = self.keycloak_client.realm_client.get_users()
        return users

    def get_user_info(self, user_id, client_ids):
        """获取用户信息"""
        user_info = self.keycloak_client.realm_client.get_user(user_id)
        roles = self.get_user_roles(client_ids, user_id)
        rules = UserRule.objects.filter(username=user_info["username"]).values(
            "group_rule__group_id", "group_rule_id", "group_rule__app"
        )
        group_rule_map = {}
        for rule in rules:
            group_rule_map.setdefault(rule["group_rule__group_id"], {}).setdefault(rule["group_rule__app"], []).append(
                rule["group_rule_id"]
            )
        try:
            groups = self.keycloak_client.realm_client.get_user_groups(user_id)
            for i in groups:
                i["rules"] = group_rule_map.get(i["id"], {})
        except Exception:
            groups = []
            # 用户补充用户组信息
        user_info.update(roles=roles)
        user_info.update(groups=groups)

        return user_info

    def get_user_roles(self, client_ids, user_id):
        user_roles = self.keycloak_client.get_realm_roles_of_user(user_id)
        role_map = {role["id"]: role["name"] for role in user_roles}

        # Fetch policies once
        policies = []
        for client_id in client_ids:
            policies.extend(self.keycloak_client.realm_client.get_client_authz_policies(client_id))

        # Build policy map for quick lookup
        policy_map = {
            role_obj["id"]: policy
            for policy in policies
            for role_obj in json.loads(policy["config"].get("roles", "[]"))
        }

        # Assemble roles list
        roles = [
            {
                "policy_id": policy_map[role_id]["id"] if role_id in policy_map else [],
                "display_name": policy_map[role_id]["name"] if role_id in policy_map else [],
                "role_id": role_id,
                "role_name": role_name,
            }
            for role_id, role_name in role_map.items()
        ]

        return roles

    def user_list_by_role(self, role_name):
        """获取角色下用户"""
        result = self.keycloak_client.realm_client.get_realm_role_members(role_name)
        return result

    def reset_pwd(self, data):
        res = self.keycloak_client.realm_client.set_user_password(data["id"], data["password"], data["temporary"])
        return res

    def user_create(self, data):
        """创建用户"""
        roles = data.pop("roles", [])
        groups = data.pop("groups", [])
        data["enabled"] = True
        data["firstName"] = data["lastName"]
        rules = data.pop("rules", [])
        if rules:
            add_rule = [UserRule(username=data["username"], group_rule_id=i) for i in rules]
            UserRule.objects.bulk_create(add_rule, batch_size=100)
        user_id = self.keycloak_client.realm_client.create_user(data)
        self.keycloak_client.realm_client.assign_realm_roles(user_id, roles)
        for group_id in groups:
            self.keycloak_client.realm_client.group_user_add(user_id, group_id)
        user_info = self.keycloak_client.realm_client.get_user(user_id)
        return user_info

    def user_delete(self, user_ids):
        """删除用户"""
        for user_id in user_ids:
            self.delete_user_cache(user_id)
            self.keycloak_client.realm_client.delete_user(user_id)

    def user_update(self, data, user_id):
        """更新用户"""
        roles = data.pop("roles", [])
        groups = data.pop("groups", [])
        data["firstName"] = data["lastName"]
        rules = data.pop("rules", [])
        UserRule.objects.filter(username=data["username"]).delete()
        old_groups = self.keycloak_client.realm_client.get_user_groups(user_id)
        old_roles = self.keycloak_client.get_realm_roles_of_user(user_id)
        for i in old_groups:
            self.keycloak_client.realm_client.group_user_remove(user_id, i["id"])
        old_roles = [i for i in old_roles if i["name"] != "admin"]
        for i in old_roles:
            i.pop("role_type", "")
        self.keycloak_client.realm_client.delete_realm_roles_of_user(user_id, old_roles)
        self.keycloak_client.realm_client.update_user(user_id, data)
        self.keycloak_client.realm_client.assign_realm_roles(user_id, roles)
        for group_id in groups:
            self.keycloak_client.realm_client.group_user_add(user_id, group_id)
        self.delete_user_cache(user_id)
        if rules:
            add_rule = [UserRule(username=data["username"], group_rule_id=i) for i in rules]
            UserRule.objects.bulk_create(add_rule, batch_size=100)

    def delete_user_cache(self, user_id):
        userinfo = self.keycloak_client.realm_client.get_user(user_id)
        keys = RoleManage.get_cache_keys(userinfo["username"])
        cache.delete_many(keys)

    def user_reset_password(self, data, user_id):
        """重置用户密码"""
        self.keycloak_client.realm_client.set_user_password(user_id, data["password"], False)

    def user_add_groups(self, data, user_id):
        """为用户添加一些组"""
        for group_id in data:
            self.keycloak_client.realm_client.group_user_add(user_id, group_id)

    def user_remove_groups(self, data, user_id):
        """将用户从一些组中移除"""
        for group_id in data:
            self.keycloak_client.realm_client.group_user_remove(user_id, group_id)

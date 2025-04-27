from django.utils.translation import gettext as _

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.system_mgmt.utils.keycloak_client import KeyCloakClient


class GroupManage(object):
    def __init__(self):
        self.keycloak_client = KeyCloakClient()

    def group_list(self, query_params=None):
        """用户组列表"""
        if not query_params:
            query_params = {"search": ""}
        groups = self.keycloak_client.realm_client.get_groups(query_params)
        return groups

    def group_retrieve(self, group_id):
        """查询某个组织的信息"""
        group = self.keycloak_client.realm_client.get_group(group_id)
        return group

    def group_create(self, data):
        """创建用户组"""
        group_id = self.keycloak_client.realm_client.create_group(
            {"name": data["group_name"]}, data.get("parent_group_id") or None
        )
        group = self.keycloak_client.realm_client.get_group(group_id)
        return group

    def group_update(self, data):
        """更新用户组"""
        self.keycloak_client.realm_client.update_group(data["group_id"], {"name": data["group_name"]})

    def group_delete(self, group_obj):
        """
        删除用户组
        1.校验用户组下是否存在用户
        2.删除操作
        """
        users = self.get_sub_group_users(group_obj)
        if users:
            raise BaseAppException(_("This group or sub groups has users, please remove the users first!"))
        group_id = group_obj["id"]
        self.keycloak_client.realm_client.delete_group(group_id)

    def get_sub_group_users(self, group_obj):
        """获取子组下用户"""
        users = self.keycloak_client.realm_client.get_group_members(group_obj["id"])
        for i in group_obj["subGroups"]:
            users += self.get_sub_group_users(i)
            if i["subGroups"]:
                self.get_sub_group_users(i)
        return users

    def group_users(self, group_id):
        """获取用户组下用户"""
        users = self.keycloak_client.realm_client.get_group_members(group_id)
        return users

    def group_add_users(self, data, group_id):
        """将一些用户添加到组"""
        if not data:
            raise BaseAppException("参数验证失败!")

        users = []
        for user_id in data:
            self.keycloak_client.realm_client.group_user_add(user_id, group_id)
            user = self.keycloak_client.realm_client.get_user(user_id)
            users.append(user["username"])

        return {"id": group_id}

    def group_remove_users(self, data, group_id):
        """将一些用户从组中移除"""
        if not data:
            raise BaseAppException("参数验证失败!")

        users = []
        for user_id in data:
            self.keycloak_client.realm_client.group_user_remove(user_id, group_id)
            user = self.keycloak_client.realm_client.get_user(user_id)
            users.append(user["username"])

        return {"id": group_id}

    def group_roles(self, group_id):
        """获取组下面的角色"""
        roles = self.keycloak_client.realm_client.get_group_realm_roles(group_id)
        return roles

    def group_add_roles(self, data, group_id):
        """将一些角色添加到组"""
        if not data:
            raise BaseAppException("参数验证失败!")
        roles = self.keycloak_client.get_realm_roles()
        role_list = [i for i in roles if i["id"] in data]

        self.keycloak_client.realm_client.assign_group_realm_roles(group_id, role_list)

        return {"id": group_id}

    def group_remove_roles(self, data, group_id):
        """将一些角色从组中移除"""
        if not data:
            raise BaseAppException("参数验证失败!")

        roles = self.get_realm_roles()
        role_list = [i for i in roles if i["id"] in data]

        self.keycloak_client.realm_client.delete_group_realm_roles(group_id, role_list)

        return {"id": group_id}

    def get_group_id_and_subgroup_id(self, group_id: str):
        """获取组织ID与子组ID的列表"""
        group_list = self.group_list()
        if group_list:
            sub_group = self.get_subgroup(group_list[0], group_id)
        else:
            sub_group = None
        group_id_list = [group_id]
        if not sub_group:
            return group_id_list
        self.get_all_group_id_by_subgroups(sub_group["subGroups"], group_id_list)
        return group_id_list

    def get_subgroup(self, group, group_id):
        """根据子组ID获取子组"""

        if group["id"] == group_id:
            return group

        for subgroup in group["subGroups"]:
            if subgroup["id"] == group_id:
                return subgroup
            elif subgroup["subGroups"]:
                for subgroup in group["subGroups"]:
                    result = self.get_subgroup(subgroup, group_id)
                    if result:
                        return result
        return None

    def get_all_group_id_by_subgroups(self, subgroups: list, id_list: list):
        """取出所有子组ID"""
        for subgroup in subgroups:
            id_list.append(subgroup["id"])
            if subgroup["subGroups"]:
                self.get_all_group_id_by_subgroups(subgroup["subGroups"], id_list)

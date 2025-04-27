# from apps.core.utils.keycloak_client import KeyCloakClient
from apps.rpc.system_mgmt import SystemMgmt


class SubGroup:
    def __init__(self, group_id, group_list):
        self.group_id = group_id
        self.group_list = group_list

    def get_group_id_and_subgroup_id(self):
        """获取组织ID与子组ID的列表"""

        sub_group = None

        for group in self.group_list:
            sub_group = self.get_subgroup(group, self.group_id)
            if sub_group:
                break

        group_id_list = [self.group_id]

        if not sub_group:
            return group_id_list

        self.get_all_group_id_by_subgroups(sub_group["subGroups"], group_id_list)

        return group_id_list

    def get_subgroup(self, group, id):
        """根据子组ID获取子组"""

        if group["id"] == id:
            return group

        for subgroup in group["subGroups"]:
            if subgroup["id"] == id:
                return subgroup
            elif subgroup["subGroups"]:
                for subgroup in group["subGroups"]:
                    result = self.get_subgroup(subgroup, id)
                    if result:
                        return result
        return None

    def get_all_group_id_by_subgroups(self, subgroups: list, id_list: list):
        """取出所有子组ID"""
        for subgroup in subgroups:
            id_list.append(subgroup["id"])
            if subgroup["subGroups"]:
                self.get_all_group_id_by_subgroups(subgroup["subGroups"], id_list)


class Group:
    def __init__(self, token):
        self.token = token
        # self.keycloak_client = KeyCloakClient()
        self.system_mgmt_client = SystemMgmt()

    def get_group_list(self):
        """获取组织列表"""
        groups = self.system_mgmt_client.search_groups({"search": ""})
        return groups["data"] if groups else []

    # def get_user_group_list(self):
    #     """获取用户组织列表"""
    #     userinfo = self.keycloak_client.get_userinfo(self.token)
    #     user_group_list = self.keycloak_client.realm_client.get_user_groups(userinfo["sub"])
    #     return user_group_list

    def get_user_group_and_subgroup_ids(self, user_group_list=[]):
        """获取用户组织ID与子组ID的列表"""
        # 获取所有组织列表
        all_groups = self.get_group_list()

        # 获取用户组织ID与子组ID的列表
        user_group_and_subgroup_ids = []
        for group_info in user_group_list:
            group_id = group_info["id"]
            user_group_and_subgroup_ids.extend(SubGroup(group_id, all_groups).get_group_id_and_subgroup_id())
        # ID去重
        user_group_and_subgroup_ids = list(set(user_group_and_subgroup_ids))

        return user_group_and_subgroup_ids

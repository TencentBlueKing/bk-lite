from apps.core.utils.user_group import Group
from apps.rpc.system_mgmt import SystemMgmt


class UserGroup:

    @staticmethod
    def get_system_mgmt_client():
        system_mgmt_client = SystemMgmt()
        return system_mgmt_client

    @classmethod
    def user_list(cls, system_mgmt_client, query_params):
        """用户列表"""
        result = system_mgmt_client.search_users(query_params)
        data = result["data"]
        return {"count": data["count"], "users": data["users"]}

    @classmethod
    def groups_list(cls, system_mgmt_client, query_params):
        """用户组列表"""
        if query_params is None:
            query_params = {"search": ""}
        groups = system_mgmt_client.search_groups(query_params)
        return groups["data"]

    @classmethod
    def user_groups_list(cls, token, request):
        """用户组列表"""
        # 查询用户角色
        is_super_admin = request.user.is_superuser
        user_groups = request.user.group_list
        if is_super_admin:
            return dict(is_all=True, group_ids=[])
        group_ids = Group(token).get_user_group_and_subgroup_ids(user_group_list=user_groups)
        return dict(is_all=False, group_ids=group_ids)

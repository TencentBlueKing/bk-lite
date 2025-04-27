from apps.cmdb.constants import ORGANIZATION
from apps.cmdb.graph.format_type import FORMAT_TYPE
from apps.core.utils.user_group import Group
# from apps.core.utils.keycloak_client import KeyCloakClient
# from apps.rpc.system_mgmt import SystemMgmt


class PermissionManage:
    def __init__(self, token):
        self.token = token
        # self.keycloak_client = KeyCloakClient()
        # self.keycloak_client = SystemMgmt()

    def get_group_params(self):
        """获取组织条件，用于列表页查询"""
        group_ids = Group(self.token).get_user_group_and_subgroup_ids()
        method = FORMAT_TYPE.get("list[]")
        params = method({"field": ORGANIZATION, "value": group_ids})
        return params

    def get_permission_params(self, roles):
        """获取条件，用于列表页查询"""

        # 查询用户角色
        # roles = self.keycloak_client.get_roles(self.token)

        # 判断是否为超管, 超管返回空条件
        if "admin" in roles:
            return ""

        # 获取用户组织条件
        params = self.get_group_params()

        return params

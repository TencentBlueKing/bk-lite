from apps.cmdb.constants import ORGANIZATION
from apps.cmdb.graph.format_type import FORMAT_TYPE


class PermissionManage:
    def __init__(self, roles=[], user_groups=[]):
        self.roles = roles
        self.user_groups = user_groups

    def get_group_params(self):
        """获取组织条件，用于列表页查询"""
        group_ids = [group["id"] for group in self.user_groups]
        method = FORMAT_TYPE.get("list[]")
        params = method({"field": ORGANIZATION, "value": group_ids})
        return params

    def get_permission_params(self):
        """获取基础权限条件，用于列表页查询（作为必须的组织权限过滤）admin用户也会受到他当前组的限制"""
        # 判断是否为超管, 超管返回空条件
        # if "admin" in self.roles:
        #     return ""
        # 获取用户组织条件
        params = self.get_group_params()
        return params


class InstancePermissionManage:

    @staticmethod
    def get_task_permissions(rules):
        """
        获取任务的权限
        :param rules: 用户规则
        :return: 权限列表
        """
        result = {}
        if not rules:
            return result
        for task_type, rule in rules.items():
            _all = any([True for i in rule if i["id"] in {"0"}])
            if not _all:
                result[task_type] = {i["id"]: i["permission"] for i in rule}

        return result

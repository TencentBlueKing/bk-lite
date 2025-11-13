# -- coding: utf-8 --
# @File: permission.py
# @Time: 2025/7/16 15:17
# @Author: windyzhao
from rest_framework.permissions import BasePermission

from apps.cmdb.utils.base import get_cmdb_rules


class InstanceTaskPermission(BasePermission):
    """
    实例权限
    InstanceTaskPermission is used to check if the user has permission to perform operations on instance tasks.
    """

    @property
    def operator_actions(self):
        """
        操作类型的action
        """
        return ["update", "destroy", "exec_task"]

    def has_object_permission(self, request, view, obj):
        rules = get_cmdb_rules(request)
        obj_rule = rules.get(obj.task_type, {})
        if not obj_rule:
            return True

        if view.action in self.operator_actions:
            _all, has_permission_ids = self.format_permission(obj_rule, "Operator")
        else:
            _all, has_permission_ids = self.format_permission(obj_rule, "View")

        if _all:
            return True
        if str(obj.id) in has_permission_ids:
            return True

        return False

    @staticmethod
    def format_permission(obj_rule, operator):
        _all = False
        has_permission_ids = []

        for _rule in obj_rule:
            if not _all and operator in _rule.get("permission", {}) and _rule["id"] in ["0"]:
                _all = True
            if _rule["id"] not in ["0"]:
                if operator in _rule.get("permission", []):
                    has_permission_ids.append(_rule["id"])

        return _all, has_permission_ids

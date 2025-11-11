# -- coding: utf-8 --
# @File: base_filters.py
# @Time: 2025/11/5 14:30
# @Author: windyzhao
from django.db.models import Q
from django_filters import FilterSet

from apps.core.utils.permission_utils import get_permission_rules
from apps.operation_analysis.constants.constants import APP_NAME


class GroupPermissionMixin:
    """
    组织权限混入类
    提供统一的组织权限验证和过滤方法
    """

    @staticmethod
    def validate_all_groups_permission(request):
        if request.method == 'GET':
            if request.GET.get('all_groups'):  # 带有 all_groups 参数，表示请求所有组织数据
                return True, None

        return False, None

    @staticmethod
    def validate_group_permission(request):
        """
        验证用户的组织权限
        
        :param request: Django request 对象
        :return: (is_valid, current_team) 元组
                 is_valid: 是否有效
                 current_team: 当前组织ID (超级用户返回 None)
        """
        _all, _current_team = GroupPermissionMixin.validate_all_groups_permission(request)
        if _all:
            return True, None

        if not request or not hasattr(request, 'user'):
            return False, None

        # user = request.user
        #
        # # 超级用户无需验证，返回 None 表示可以访问所有数据
        # if getattr(user, 'is_superuser', False):
        #     return True, None

        # 获取当前选中的组织
        current_team = request.COOKIES.get("current_team")

        if not current_team:
            return False, None

        try:
            current_team = int(current_team)
        except (ValueError, TypeError):
            return False, None

        # 验证用户权限
        # user_group_list = getattr(user, 'group_list', [])
        # if current_team not in user_group_list:
        #     return False, None

        return True, current_team

    @classmethod
    def apply_group_filter(cls, queryset, current_team, user="", permission_key=""):
        """
        对查询集应用组织过滤

        :param queryset: Django QuerySet
        :param current_team: 当前组织ID (None 表示超级用户,不过滤)
        :param permission_key: 权限键，用于获取实例级权限
        :param user: 当前用户
        :return: 过滤后的 QuerySet

        示例:
        - groups 字段值: [1, 2, 3]
        - current_team: 1
        - 结果: 查询包含 1 的所有记录

        过滤逻辑:
        - 必须满足组织权限 (groups__contains=current_team) AND
        - 必须满足 (实例级权限 id__in OR 创建者是当前用户 created_by)
        """

        if current_team is None:
            # 超级用户,返回所有数据
            return queryset

        # 第一层: 必须在当前组织下
        queryset = queryset.filter(groups__contains=int(current_team))

        # 第二层: 构建或查询条件 (实例级权限 OR 创建者权限)
        permission_q = Q()
        if user:
            # 如果提供了实例ID列表,添加实例级权限查询
            id_list = cls.get_permission_rules(current_team=current_team, user=user,
                                               permission_key=permission_key)
            if id_list:
                permission_q |= Q(id__in=id_list)

            # 如果提供了创建者,添加创建者查询
            created_by = getattr(user, "username", None)
            if created_by:
                permission_q |= Q(created_by=created_by)

        # 只有当存在权限条件时才应用过滤
        if permission_q:
            queryset = queryset.filter(permission_q)

        return queryset

    @staticmethod
    def get_permission_rules(current_team, user, permission_key):
        """
        获取当前用户的组织权限规则

        :param current_team: 当前组织ID
        :param user: 用户名
        :param permission_key: 权限键
        :return: 组织权限规则列表
        """
        _permission_rules = {}
        if permission_key:
            _permission_rules = get_permission_rules(user=user,
                                                     current_team=current_team, app_name=APP_NAME,
                                                     permission_key=permission_key)
            """
            {'instance': [{'id': 3, 'name': '【目录A】监控222', 'permission': ['View', 'Operate']}], 'team': []}
            """

        result = [item['id'] for item in _permission_rules.get('instance', [])]
        return result


class BaseGroupFilter(FilterSet):
    """
    基础组织过滤器
    自动根据当前用户的组织权限过滤数据
    """

    @property
    def filter_name_map(self):
        return {
            "DashboardModelFilter": "directory.dashboard",
            "TopologyModelFilter": "directory.topology",
            "ArchitectureModelFilter": "directory.architecture",
            "DataSourceAPIModelFilter": "datasource"

        }

    def permission_key(self):
        filter_name = self.__class__.__name__
        return self.filter_name_map.get(filter_name)

    @property
    def is_directory(self):
        filter_name = self.__class__.__name__
        return filter_name == "DirectoryModelFilter"

    @property
    def qs(self):
        """重写查询集,添加组织过滤"""
        queryset = super().qs
        return queryset
        # request = getattr(self, 'request', None)
        #
        # not_check_permission, _ = GroupPermissionMixin.validate_all_groups_permission(request)
        # if not_check_permission:
        #     return queryset
        #
        # # if self.is_directory:
        # #     return queryset
        #
        # # 验证权限
        # is_valid, current_team = GroupPermissionMixin.validate_group_permission(request)
        #
        # if not is_valid:
        #     return queryset.none()
        #
        # current_team = request.COOKIES.get("current_team")
        # _permission_key = self.permission_key()
        #
        # # 应用组织过滤
        # return GroupPermissionMixin.apply_group_filter(queryset=queryset, current_team=current_team,
        #                                                permission_key=_permission_key,
        #                                                user=request.user)

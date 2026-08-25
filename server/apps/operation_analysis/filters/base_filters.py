# -- coding: utf-8 --
# @File: base_filters.py
# @Time: 2025/11/5 14:30
# @Author: windyzhao
from django.db.models import Q
from django_filters import FilterSet

from apps.core.utils.team_utils import get_current_team


class GroupPermissionMixin:
    """
    组织权限混入类
    提供统一的组织权限验证和过滤方法
    """

    @staticmethod
    def validate_all_groups_permission(request):
        if request.method == "GET":
            if request.GET.get("all_groups"):  # 带有 all_groups 参数，表示请求所有组织数据
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

        if not request or not hasattr(request, "user"):
            return False, None

        # 获取当前选中的组织
        current_team = get_current_team(request)

        if not current_team:
            return False, None

        try:
            current_team = int(current_team)
        except (ValueError, TypeError):
            return False, None

        return True, current_team

    @classmethod
    def apply_group_filter(cls, queryset, current_team, user="", permission_key="", group_ids=None):
        """
        对查询集应用组织过滤

        :param queryset: Django QuerySet
        :param current_team: 当前组织ID (None 表示超级用户,不过滤)
        :param permission_key: 兼容旧调用方，已忽略（可见性不按实例/个人收紧）
        :param user: 兼容旧调用方，已忽略（可见性不按创建人收紧）
        :param group_ids: 扩展的组织ID列表（用于 include_children），传入时使用 OR 查询
        :return: 过滤后的 QuerySet

        过滤逻辑:
        - 仅按组织归属过滤 (groups 包含 current_team / group_ids)
        - 不按实例数据权限或 created_by 收缩可见范围
        """

        if current_team is None:
            # 超级用户,返回所有数据
            return queryset

        if group_ids and len(group_ids) > 1:
            org_query = Q()
            for gid in group_ids:
                org_query |= Q(groups__contains=int(gid))
            return queryset.filter(org_query)

        return queryset.filter(groups__contains=int(current_team))


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
            "ScreenModelFilter": "directory.screen",
            "ReportModelFilter": "directory.report",
            "DataSourceAPIModelFilter": "datasource",
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

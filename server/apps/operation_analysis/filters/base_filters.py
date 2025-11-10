# -- coding: utf-8 --
# @File: base_filters.py
# @Time: 2025/11/5 14:30
# @Author: windyzhao

from django_filters import FilterSet


class GroupPermissionMixin:
    """
    组织权限混入类
    提供统一的组织权限验证和过滤方法
    """

    @staticmethod
    def validate_group_permission(request):
        """
        验证用户的组织权限
        
        :param request: Django request 对象
        :return: (is_valid, current_team) 元组
                 is_valid: 是否有效
                 current_team: 当前组织ID (超级用户返回 None)
        """
        if request.method == 'GET':
            if request.GET.get('all_groups'): # 带有 all_groups 参数，表示请求所有组织数据
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

    @staticmethod
    def apply_group_filter(queryset, current_team):
        """
        对查询集应用组织过滤
        
        :param queryset: Django QuerySet
        :param current_team: 当前组织ID (None 表示超级用户，不过滤)
        :return: 过滤后的 QuerySet
        
        示例：
        - groups 字段值: [1, 2, 3]
        - current_team: 1
        - 结果: 查询包含 1 的所有记录
        """
        if current_team is None:
            # 超级用户，返回所有数据
            return queryset

        # 使用 Django ORM 的 __contains 查询
        # groups__contains 表示 groups 数组包含指定的值
        return queryset.filter(groups__contains=int(current_team))


class BaseGroupFilter(FilterSet):
    """
    基础组织过滤器
    自动根据当前用户的组织权限过滤数据
    """

    @property
    def qs(self):
        """重写查询集,添加组织过滤"""
        queryset = super().qs
        request = getattr(self, 'request', None)

        # 验证权限
        is_valid, current_team = GroupPermissionMixin.validate_group_permission(request)
        
        if not is_valid:
            return queryset.none()
        
        # 应用组织过滤
        return GroupPermissionMixin.apply_group_filter(queryset, current_team)

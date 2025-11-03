"""
组织级联查询混合类
提供统一的组织权限过滤方法，确保查询集合与"选择组织 + 用户权限"一致
"""
from apps.core.logger import logger
from apps.system_mgmt.utils.group_utils import GroupUtils


class GroupQueryMixin:
    """
    组织级联查询混合类

    使用说明:
    1. 在ViewSet中继承此Mixin
    2. 调用get_query_groups方法获取查询的组织列表
    3. 使用返回的组织列表进行数据过滤

    示例:
        class MyViewSet(OrganizationQueryMixin, viewsets.ModelViewSet):
            def list(self, request, *args, **kwargs):
                # 获取查询组织列表（从请求参数中获取include_children）
                query_groups = self.get_query_groups(request)

                # 使用组织列表过滤数据
                queryset = self.queryset.filter(team__in=query_groups)
                ...
    """

    def get_query_groups(self, request):
        """
        获取用于数据查询的组织ID列表

        规则说明:
        - 当不勾选"包含子组织"时，仅查询当前组织的所有数据
        - 勾选"包含子组织"后，查询的数据范围为：当前组织数据 + 有权限的子组织数据
        - 注意：不是查询所有的子组织，而是用户有权限的子组织，并且向下递归查询

        :param request: Django request对象
        :param include_children: 是否包含子组织，如果为None则从请求参数中获取
        :return: 组织ID列表
        """
        # 1. 获取当前选中的组织ID（从cookies中获取）
        current_team = request.COOKIES.get("current_team")
        if not current_team:
            logger.warning("未找到current_team参数，返回空组织列表")
            return []

        try:
            current_team = int(current_team)
        except (ValueError, TypeError):
            logger.error(f"current_team参数格式错误: {current_team}")
            return []

        include_children = request.COOKIES.get("include_children", "0") == "1"
        # 3. 获取用户有权限的组织列表
        user_group_list = self._get_user_group_list(request)

        # 4. 使用GroupUtils获取最终的查询组织列表
        query_groups = GroupUtils.get_user_authorized_child_groups(
            user_group_list=user_group_list, target_group_id=current_team, include_children=include_children
        )

        if not query_groups:
            logger.warning(f"用户对组织 {current_team} 没有权限或该组织不存在")

        return query_groups

    @staticmethod
    def _get_user_group_list(request):
        """
        获取用户有权限的组织列表

        :param request: Django request对象
        :return: 用户组织ID列表
        """
        # 如果是超级用户，获取所有组织
        if hasattr(request.user, "is_superuser") and request.user.is_superuser:
            from apps.system_mgmt.models import Group

            return list(Group.objects.values_list("id", flat=True))

        # 普通用户，从user.group_list获取
        if hasattr(request.user, "group_list"):
            return request.user.group_list or []

        logger.warning(f"无法获取用户 {request.user.username} 的组织列表")
        return []

    def filter_by_groups(self, queryset, request):
        """
        便捷方法：直接对queryset进行组织过滤

        :param queryset: Django QuerySet对象
        :param request: Django request对象
        :return: 过滤后的QuerySet
        """
        query_groups = self.get_query_groups(request)

        if not query_groups:
            # 返回空查询集
            return queryset.none()

        # 根据字段类型选择过滤方式
        # 如果是JSONField（列表），使用overlap查询
        # 如果是ForeignKey，使用in查询
        filter_kwargs = {"team__overlap": query_groups}

        try:
            return queryset.filter(**filter_kwargs)
        except Exception:
            # 如果overlap失败，尝试使用in查询
            filter_kwargs = {"team__in": query_groups}
            return queryset.filter(**filter_kwargs)

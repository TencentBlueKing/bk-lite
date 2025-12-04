from django.db.models import Q

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group, User


class GroupFilterMixin:
    """
    组过滤混入类

    为日志类ViewSet提供基于current_team cookie的组过滤功能。
    通过username+domain组合条件筛选组内用户的日志。
    支持递归获取子组用户（通过include_children cookie控制）。
    """

    def _get_child_group_ids(self, parent_id, group_model):
        """
        递归获取所有子组ID

        Args:
            parent_id: 父组ID
            group_model: Group模型类

        Returns:
            set: 包含父组及所有子孙组的ID集合
        """
        group_ids = {parent_id}

        # 查找直接子组
        child_groups = group_model.objects.filter(parent_id=parent_id)

        # 递归获取每个子组的子组
        for child in child_groups:
            group_ids.update(self._get_child_group_ids(child.id, group_model))

        return group_ids

    def get_queryset(self):
        """
        重写queryset获取逻辑，添加组过滤
        从request.COOKIES.get('current_team')获取当前组，筛选组下用户的日志
        支持递归获取子组用户（通过include_children cookie控制）
        """
        queryset = super().get_queryset()

        # 从Cookie中获取当前组ID
        current_team = self.request.COOKIES.get("current_team")

        if not current_team:
            logger.debug("未找到current_team cookie，返回全部日志")
            return queryset

        try:
            team_id = int(current_team)

            # 获取是否需要递归查询子组
            include_children = self.request.COOKIES.get("include_children", "0") == "1"
            logger.debug(f"当前组ID: {team_id}, 递归子组: {include_children}")

            # 确定需要查询的组ID集合
            if include_children:
                # 递归获取当前组及所有子组的ID
                group_ids = self._get_child_group_ids(team_id, Group)
                logger.debug(f"递归获取到的组ID集合: {group_ids}")
            else:
                # 仅查询当前组
                group_ids = {team_id}

            # 查询属于这些组的所有用户（group_list包含任一组ID）
            user_conditions_for_groups = Q()
            for gid in group_ids:
                user_conditions_for_groups |= Q(group_list__contains=[gid])

            users_in_group = User.objects.filter(user_conditions_for_groups)
            user_count = users_in_group.count()
            logger.debug(f"找到 {user_count} 个用户属于组 {group_ids}")

            # 构建username和domain的组合条件（因为username+domain才能确定唯一用户）
            user_conditions = Q()
            for user in users_in_group:
                user_conditions |= Q(username=user.username, domain=user.domain)

            if user_conditions:
                queryset = queryset.filter(user_conditions)
                logger.debug(f"按组过滤后的日志数量: {queryset.count()}")
            else:
                # 如果组内没有用户，返回空查询集
                logger.debug(f"组{group_ids}中没有用户，返回空结果")
                queryset = queryset.none()

        except (ValueError, TypeError) as e:
            logger.warning(f"解析current_team失败: {current_team}, 错误: {str(e)}")
            # 解析失败时返回全部日志
            pass

        return queryset

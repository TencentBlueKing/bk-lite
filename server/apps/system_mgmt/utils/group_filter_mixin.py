from django.db.models import Q
from django.http import JsonResponse
from rest_framework.exceptions import PermissionDenied

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.team_utils import get_current_team
from apps.system_mgmt.models import Group, User


class GroupPermissionMixin:
    """
    组权限校验混入类

    为 ViewSet 提供基于用户 group_list 的权限校验功能。
    用于校验用户是否有权限访问指定的组、用户或数据。

    主要方法：
    - _get_user_group_ids: 获取用户有权限的组ID集合
    - _validate_group_permission: 校验用户是否有权限访问指定组
    - _validate_user_in_accessible_groups: 校验目标用户是否属于当前用户有权限的组
    - _filter_by_accessible_groups: 按用户有权限的组筛选查询集
    """

    def _get_user_group_ids(self, user):
        """获取用户有权限的组ID集合

        Args:
            user: 当前用户对象

        Returns:
            set: 用户有权限的组ID集合
        """
        if getattr(user, "is_superuser", False):
            return None  # superuser 返回 None 表示有权限访问所有组
        return {g["id"] for g in getattr(user, "group_list", [])}

    def _validate_group_permission(self, user, group_id, loader=None):
        """校验用户是否有权限访问指定组

        Args:
            user: 当前用户对象
            group_id: 要校验的组ID
            loader: 语言加载器（可选）

        Returns:
            tuple: (is_valid, error_response)
                   is_valid: 是否有权限
                   error_response: 错误响应（如果无权限）
        """
        if getattr(user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(user)
        if group_id not in user_group_ids:
            message = loader.get("error.no_permission_access_group") if loader else "无权访问该组织"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _validate_user_in_accessible_groups(self, current_user, target_user, loader=None):
        """校验目标用户是否属于当前用户有权限的组

        Args:
            current_user: 当前用户对象
            target_user: 目标用户对象（User model instance）
            loader: 语言加载器（可选）

        Returns:
            tuple: (is_valid, error_response)
                   is_valid: 是否有权限
                   error_response: 错误响应（如果无权限）
        """
        if getattr(current_user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(current_user)
        target_group_ids = set(target_user.group_list or [])

        # 检查目标用户的组是否与当前用户的组有交集
        if not user_group_ids.intersection(target_group_ids):
            message = loader.get("error.no_permission_access_user") if loader else "无权访问该用户"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _filter_by_accessible_groups(self, queryset, user, group_field="group_list"):
        """按用户有权限的组筛选查询集

        Args:
            queryset: 原始查询集
            user: 当前用户对象
            group_field: 组字段名（默认 group_list）

        Returns:
            QuerySet: 筛选后的查询集
        """
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        # 构建查询条件：group_list 与用户有权限的组有交集
        query = Q()
        for group_id in user_group_ids:
            query |= Q(**{f"{group_field}__contains": group_id})
        return queryset.filter(query)


class GroupFilterMixin:
    """
    组过滤混入类

    为日志类ViewSet提供基于current_team cookie的组过滤功能。
    通过username+domain组合条件筛选组内用户的日志。
    支持递归获取子组用户（通过include_children cookie控制）。

    安全机制：
    - 验证 current_team 必须存在且有效
    - 验证 current_team 必须属于当前用户的 group_list（superuser 豁免）
    - 防止跨组织数据泄露
    """

    def _parse_current_team_cookie(self, request, default=0):
        """解析 current_team（优先读 API Key 注入属性，回退到 cookie）"""
        current_team = get_current_team(request, str(default))
        try:
            return int(current_team)
        except (TypeError, ValueError):
            return default

    def _validate_current_team_permission(self, request):
        """验证用户有权限访问 current_team，返回 current_team 值

        - 如果 current_team 无效或用户无权访问，抛出 PermissionDenied
        - superuser 跳过 group_list 验证，但仍需要有效的 current_team
        """
        current_team = self._parse_current_team_cookie(request)
        if not current_team:
            raise PermissionDenied("无权访问该团队数据")
        if not getattr(request.user, "is_superuser", False):
            user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
            if current_team not in user_group_ids:
                raise PermissionDenied("无权访问该团队数据")
        return current_team

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

        安全机制：
        - 验证 current_team 必须属于当前用户的 group_list
        - 无效或无权限的 current_team 将抛出 PermissionDenied
        """
        queryset = super().get_queryset()

        # 验证 current_team 权限（会抛出 PermissionDenied 如果无权限）
        team_id = self._validate_current_team_permission(self.request)

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

        return queryset

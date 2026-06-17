"""Mixin for team permission validation in ViewSets."""

from rest_framework.exceptions import PermissionDenied

from apps.opspilot.models import Bot


class TeamPermissionMixin:
    """Mixin providing team permission validation for ViewSets.

    Provides lightweight permission validation without inheriting full AuthViewSet functionality.
    Use this for ViewSets that don't need AuthViewSet's list/query_by_groups features.

    If the ViewSet has a `loader` attribute (e.g., from LanguageViewSet), it will be used
    for i18n error messages.
    """

    def _parse_current_team_cookie(self, request, default=0):
        """解析 current_team cookie"""
        current_team = request.COOKIES.get("current_team", str(default))
        try:
            return int(current_team)
        except (TypeError, ValueError):
            return default

    def _get_permission_error_message(self):
        """获取权限错误消息，支持 i18n"""
        loader = getattr(self, "loader", None)
        if loader:
            return loader.get("error.no_permission_access_team") or "无权访问该团队数据"
        return "无权访问该团队数据"

    def _validate_current_team_permission(self, request):
        """验证用户有权限访问 current_team，返回 current_team 值

        - 如果 current_team 无效或用户无权访问，抛出 PermissionDenied
        - superuser 跳过 group_list 验证，但仍需要有效的 current_team
        """
        current_team = self._parse_current_team_cookie(request)
        if not current_team:
            raise PermissionDenied(self._get_permission_error_message())
        if not getattr(request.user, "is_superuser", False):
            user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
            if current_team not in user_group_ids:
                raise PermissionDenied(self._get_permission_error_message())
        return current_team

    def _validate_bot_permission(self, request, bot_id):
        """验证用户有权限访问指定的 bot"""
        loader = getattr(self, "loader", None)
        current_team = self._validate_current_team_permission(request)
        bot = Bot.objects.filter(id=bot_id).first()
        if not bot:
            msg = loader.get("error.bot_not_found") if loader else "Bot 不存在"
            raise PermissionDenied(msg)
        if current_team not in (bot.team or []):
            msg = loader.get("error.no_permission_access_bot") if loader else "无权访问该 Bot 的数据"
            raise PermissionDenied(msg)
        return current_team

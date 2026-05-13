"""Mixin for pin-related functionality in ViewSets."""

from typing import TYPE_CHECKING, Optional

from django.db.models import Case, IntegerField, QuerySet, Value, When
from django.http import JsonResponse

from apps.opspilot.models import UserPin

if TYPE_CHECKING:
    from apps.core.utils.loader import LanguageLoader


class PinMixin:
    """Mixin providing pin functionality for ViewSets.

    Requires the ViewSet to have:
    - self.loader: Language loader for error messages
    - self._validate_current_team_permission(request): Method to validate team permission
    - self.get_has_permission(user, instance, current_team, include_children): Method to check permission
    - self.get_object(): Method to get the current instance
    - self.get_queryset_by_permission(request, queryset): Method to filter queryset by permission
    - self._list(queryset): Method to return paginated list response
    """

    # Type hints for attributes provided by AuthViewSet
    loader: Optional["LanguageLoader"]

    # Subclasses must define these
    pin_content_type: str
    pin_permission_error_key: str = "error.permission_update_denied"  # i18n key for permission error

    def query_by_groups_with_pinned(self, request, queryset):
        """根据用户组权限过滤查询结果，并支持置顶排序"""
        # 验证用户有权限访问 current_team（superuser 跳过验证）
        if not getattr(request.user, "is_superuser", False):
            self._validate_current_team_permission(request)
        new_queryset = self.get_queryset_by_permission(request, queryset)
        # 如果返回的不是 QuerySet（如 JsonResponse），直接返回
        if not isinstance(new_queryset, QuerySet):
            return new_queryset
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        pinned_ids = list(
            UserPin.objects.filter(
                username=username,
                domain=domain,
                content_type=self.pin_content_type,
            ).values_list("object_id", flat=True)
        )
        new_queryset = new_queryset.annotate(
            is_pinned_for_user=Case(
                When(id__in=pinned_ids, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        return self._list(new_queryset.order_by("-is_pinned_for_user", "-id"))

    def toggle_pin(self, request, pk=None):
        """切换置顶状态（个人行为）"""
        instance = self.get_object()
        if not request.user.is_superuser:
            current_team = self._validate_current_team_permission(request)
            include_children = request.COOKIES.get("include_children", "0") == "1"
            has_permission = self.get_has_permission(request.user, instance, current_team, include_children=include_children)
            if not has_permission:
                message = self.loader.get(self.pin_permission_error_key) if self.loader else "You do not have permission to update this instance"
                return JsonResponse({"result": False, "message": message})
        username = request.user.username
        domain = getattr(request.user, "domain", "")
        pin_obj, created = UserPin.objects.get_or_create(
            username=username,
            domain=domain,
            content_type=self.pin_content_type,
            object_id=instance.id,
        )
        if created:
            is_pinned = True
        else:
            pin_obj.delete()
            is_pinned = False
        return JsonResponse({"result": True, "data": {"is_pinned": is_pinned}})

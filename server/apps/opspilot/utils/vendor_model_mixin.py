"""Mixin for vendor-based model query in ViewSets."""

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from apps.core.decorators.api_permission import HasPermission


class VendorModelMixin:
    """Mixin providing by_vendor action for model ViewSets.

    Requires the ViewSet to have:
    - self.loader: Language loader for error messages
    - self._parse_current_team_cookie(request): Method to parse current_team cookie
    - self._list(queryset): Method to return paginated list response
    - self.get_queryset(): Method to get the queryset
    - self.filter_queryset(queryset): Method to apply filters
    - self.ORDERING_FIELD: Field for ordering results
    """

    @action(methods=["GET"], detail=False)
    @HasPermission("provide_list-View")
    def by_vendor(self, request):
        """按供应商查询模型（配置场景，不过滤模型的 team）

        安全控制：验证用户对该供应商有权限（vendor.team 包含用户的 current_team）
        """
        vendor_id = request.query_params.get("vendor")
        if not vendor_id:
            message = self.loader.get("error.vendor_required") if self.loader else "vendor parameter is required"
            return JsonResponse({"result": False, "message": message})

        # 获取用户可见的 team 列表
        current_team = self._parse_current_team_cookie(request)
        if not current_team:
            return self._list(self.get_queryset().none())

        # 验证用户有权限访问 current_team（superuser 跳过验证）
        if not getattr(request.user, "is_superuser", False):
            user_group_ids = {g["id"] for g in getattr(request.user, "group_list", [])}
            if current_team not in user_group_ids:
                raise PermissionDenied(self.loader.get("error.no_permission_access_team") if self.loader else "无权访问该团队数据")

        # 过滤：vendor_id + vendor.team 包含用户的 team（安全校验）
        # 不过滤模型自身的 team（配置场景展示所有模型）
        queryset = self.filter_queryset(self.get_queryset()).filter(
            vendor_id=vendor_id,
            vendor__team__contains=current_team,
        )
        return self._list(queryset.order_by(self.ORDERING_FIELD))

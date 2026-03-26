from apps.cmdb.filters.subsciption import SubscriptionRuleFilter
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.serializers.subscription import SubscriptionRuleSerializer
from apps.cmdb.utils.subscription_utils import check_subscription_manage_permission
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.system_mgmt.utils.group_utils import GroupUtils
from rest_framework import viewsets
from rest_framework.decorators import action

from config.drf.pagination import CustomPageNumberPagination


class SubscriptionViewSet(viewsets.ModelViewSet):
    """订阅规则管理视图集。"""

    queryset = SubscriptionRule.objects.all().order_by("-created_at")
    serializer_class = SubscriptionRuleSerializer
    filterset_class = SubscriptionRuleFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        current_team = self.request.COOKIES.get("current_team")
        if current_team in (None, ""):
            return SubscriptionRule.objects.none()
        try:
            current_team_id = int(current_team)
        except (TypeError, ValueError):
            return SubscriptionRule.objects.none()

        org_ids = GroupUtils.get_group_with_descendants(current_team_id)
        return SubscriptionRule.objects.filter(
            organization__in=org_ids
        ).order_by("-created_at")

    @HasPermission("asset_info-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return WebUtils.response_success(
                {
                    "count": self.paginator.page.paginator.count,
                    "next": self.paginator.get_next_link(),
                    "previous": self.paginator.get_previous_link(),
                    "results": serializer.data,
                }
            )
        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(
            {
                "count": len(serializer.data),
                "next": None,
                "previous": None,
                "results": serializer.data,
            }
        )

    @HasPermission("asset_info-View")
    def retrieve(self, request, *args, **kwargs):
        data = super().retrieve(request, *args, **kwargs).data
        return WebUtils.response_success(data)

    @HasPermission("asset_info-Add")
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            created_by=request.user.username,
            updated_by=request.user.username,
            domain=request.user.domain,
            updated_by_domain=request.user.domain,
        )
        return WebUtils.response_success(serializer.data)

    @HasPermission("asset_info-Edit")
    def update(self, request, *args, **kwargs):
        rule = self.get_object()
        if not self._check_manage_permission(rule, request):
            return WebUtils.response_403("仅所属组织可管理")
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(rule, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            updated_by=request.user.username, updated_by_domain=request.user.domain
        )
        return WebUtils.response_success(serializer.data)

    @HasPermission("asset_info-Edit")
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @HasPermission("asset_info-Delete")
    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if not self._check_manage_permission(rule, request):
            return WebUtils.response_403("仅所属组织可管理")
        rule.delete()
        return WebUtils.response_success()

    @action(methods=["post"], detail=True)
    @HasPermission("asset_info-Edit")
    def toggle(self, request, pk=None):
        rule = self.get_object()
        if not self._check_manage_permission(rule, request):
            return WebUtils.response_403("仅所属组织可管理")
        rule.is_enabled = not rule.is_enabled
        rule.updated_by = request.user.username
        rule.updated_by_domain = request.user.domain
        rule.save(
            update_fields=[
                "is_enabled",
                "updated_by",
                "updated_by_domain",
                "updated_at",
            ]
        )
        serializer = self.get_serializer(rule)
        return WebUtils.response_success(serializer.data)

    @staticmethod
    def _check_manage_permission(rule: SubscriptionRule, request) -> bool:
        """检查当前用户是否有权限管理指定规则。"""
        return check_subscription_manage_permission(
            rule.organization, request.COOKIES.get("current_team")
        )

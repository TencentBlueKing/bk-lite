from rest_framework.exceptions import PermissionDenied

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)


class DashboardSubscriptionService:
    @staticmethod
    def can_view_dashboard(request, dashboard: Dashboard) -> bool:
        user = request.user
        if getattr(user, "is_superuser", False):
            return True

        current_team = get_current_team(request)
        try:
            current_team_id = int(current_team)
        except (TypeError, ValueError):
            return False

        from apps.operation_analysis.views.view import DashboardModelViewSet

        viewset = DashboardModelViewSet()
        return viewset.get_has_permission(
            user,
            dashboard,
            current_team_id,
            is_check=True,
            include_children=request.COOKIES.get("include_children", "0") == "1",
        )

    @classmethod
    def require_dashboard_view(cls, request, dashboard: Dashboard) -> None:
        if not cls.can_view_dashboard(request, dashboard):
            raise PermissionDenied("无权查看该仪表盘")

    @classmethod
    def create(cls, request, serializer) -> DashboardReportSubscription:
        dashboard = serializer.validated_data["dashboard"]
        cls.require_dashboard_view(request, dashboard)
        return serializer.save(creator=request.user.username)

    @classmethod
    def update(
        cls,
        request,
        subscription: DashboardReportSubscription,
        serializer,
    ) -> DashboardReportSubscription:
        if (
            subscription.creator != request.user.username
            and not getattr(request.user, "is_superuser", False)
        ):
            raise PermissionDenied("只能修改自己的报告订阅")
        if subscription.dashboard is None:
            raise PermissionDenied("源仪表盘已不存在，不能修改该订阅")
        cls.require_dashboard_view(request, subscription.dashboard)
        return serializer.save()

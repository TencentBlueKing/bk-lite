from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)
from apps.system_mgmt.models import Channel


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
    def validate_email_channel(cls, request, channel: Channel | None) -> None:
        if channel is None:
            raise ValidationError(
                {"email_channel": "报告订阅必须指定邮件通道"}
            )
        if channel.channel_type != "email":
            raise ValidationError(
                {"email_channel": "所选通道不是邮件类型"}
            )
        if not getattr(request.user, "is_superuser", False):
            current_team = get_current_team(request)
            try:
                current_team_id = int(current_team)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"email_channel": "无权使用该邮件通道"}
                )
            channel_teams = channel.team or []
            if current_team_id not in channel_teams:
                raise ValidationError(
                    {"email_channel": "无权使用该邮件通道"}
                )

    @classmethod
    def create(cls, request, serializer) -> DashboardReportSubscription:
        dashboard = serializer.validated_data["dashboard"]
        cls.require_dashboard_view(request, dashboard)
        cls.validate_email_channel(
            request,
            serializer.validated_data.get("email_channel"),
        )
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
        cls.validate_email_channel(
            request,
            serializer.validated_data.get(
                "email_channel",
                subscription.email_channel,
            ),
        )
        return serializer.save()

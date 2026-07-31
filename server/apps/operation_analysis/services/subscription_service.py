from rest_framework.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.core.utils.team_utils import get_current_team
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)
from apps.operation_analysis.services.schedule_calculator import (
    ScheduleSpec,
    next_run,
    validate_iana_timezone,
)
from apps.system_mgmt.models import Channel

SCHEDULE_FIELDS = frozenset(
    {
        "schedule_type",
        "schedule_hour",
        "schedule_minute",
        "schedule_weekday",
        "schedule_day_of_month",
        "timezone",
    }
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
    def build_schedule_spec(
        cls,
        *,
        schedule_type: str | None,
        schedule_hour: int | None,
        schedule_minute: int | None,
        schedule_weekday: int | None,
        schedule_day_of_month: int | None,
    ) -> ScheduleSpec | None:
        if schedule_type is None:
            return None
        if schedule_hour is None or schedule_minute is None:
            raise ValidationError(
                {"schedule_hour": "已配置调度时必须指定时分"}
            )
        return ScheduleSpec(
            schedule_type=schedule_type,
            hour=schedule_hour,
            minute=schedule_minute,
            weekday=schedule_weekday,
            day_of_month=schedule_day_of_month,
        )

    @classmethod
    def compute_next_run_at(
        cls,
        *,
        schedule_type: str | None,
        schedule_hour: int | None,
        schedule_minute: int | None,
        schedule_weekday: int | None,
        schedule_day_of_month: int | None,
        timezone_name: str | None,
        after=None,
    ):
        spec = cls.build_schedule_spec(
            schedule_type=schedule_type,
            schedule_hour=schedule_hour,
            schedule_minute=schedule_minute,
            schedule_weekday=schedule_weekday,
            schedule_day_of_month=schedule_day_of_month,
        )
        if spec is None:
            return None
        if not timezone_name:
            raise ValidationError(
                {"timezone": "已配置调度时必须指定 IANA 时区"}
            )
        try:
            tz = validate_iana_timezone(timezone_name)
            spec.validate()
        except ValueError as exc:
            raise ValidationError({"schedule_type": str(exc)}) from exc
        result = next_run(spec, tz, after=after or timezone.now())
        return result.utc

    @classmethod
    def _schedule_values_from_instance(
        cls, subscription: DashboardReportSubscription
    ) -> dict:
        return {
            "schedule_type": subscription.schedule_type,
            "schedule_hour": subscription.schedule_hour,
            "schedule_minute": subscription.schedule_minute,
            "schedule_weekday": subscription.schedule_weekday,
            "schedule_day_of_month": subscription.schedule_day_of_month,
            "timezone": subscription.timezone,
        }

    @classmethod
    def _merge_schedule_values(
        cls,
        subscription: DashboardReportSubscription | None,
        validated_data: dict,
    ) -> dict:
        base = (
            cls._schedule_values_from_instance(subscription)
            if subscription is not None
            else {
                "schedule_type": None,
                "schedule_hour": None,
                "schedule_minute": None,
                "schedule_weekday": None,
                "schedule_day_of_month": None,
                "timezone": None,
            }
        )
        for field in SCHEDULE_FIELDS:
            if field in validated_data:
                base[field] = validated_data[field]
        return base

    @classmethod
    def _schedule_changed(
        cls,
        subscription: DashboardReportSubscription,
        validated_data: dict,
    ) -> bool:
        current = cls._schedule_values_from_instance(subscription)
        for field in SCHEDULE_FIELDS:
            if field in validated_data and validated_data[field] != current[field]:
                return True
        return False

    @classmethod
    def create(cls, request, serializer) -> DashboardReportSubscription:
        dashboard = serializer.validated_data["dashboard"]
        cls.require_dashboard_view(request, dashboard)
        cls.validate_email_channel(
            request,
            serializer.validated_data.get("email_channel"),
        )
        schedule = cls._merge_schedule_values(None, serializer.validated_data)
        next_run_at = cls.compute_next_run_at(
            schedule_type=schedule["schedule_type"],
            schedule_hour=schedule["schedule_hour"],
            schedule_minute=schedule["schedule_minute"],
            schedule_weekday=schedule["schedule_weekday"],
            schedule_day_of_month=schedule["schedule_day_of_month"],
            timezone_name=schedule["timezone"],
        )
        return serializer.save(
            creator=request.user.username,
            next_run_at=next_run_at,
            version=1,
        )

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

        expected_version = serializer.validated_data.pop("version", None)
        schedule_changed = cls._schedule_changed(
            subscription, serializer.validated_data
        )
        if schedule_changed:
            if (
                expected_version is not None
                and expected_version != subscription.version
            ):
                raise ValidationError(
                    {"version": "调度配置版本冲突，请刷新后重试"}
                )

        new_status = serializer.validated_data.get(
            "status", subscription.status
        )
        resuming = (
            subscription.status == DashboardReportSubscription.Status.PAUSED
            and new_status == DashboardReportSubscription.Status.ACTIVE
        )

        schedule = cls._merge_schedule_values(
            subscription, serializer.validated_data
        )
        extra = {}
        if schedule_changed:
            extra["next_run_at"] = cls.compute_next_run_at(
                schedule_type=schedule["schedule_type"],
                schedule_hour=schedule["schedule_hour"],
                schedule_minute=schedule["schedule_minute"],
                schedule_weekday=schedule["schedule_weekday"],
                schedule_day_of_month=schedule["schedule_day_of_month"],
                timezone_name=schedule["timezone"],
            )
            extra["version"] = subscription.version + 1
        elif resuming and schedule["schedule_type"] is not None:
            # 恢复：从恢复时刻重算未来计划，不递增 schedule version
            extra["next_run_at"] = cls.compute_next_run_at(
                schedule_type=schedule["schedule_type"],
                schedule_hour=schedule["schedule_hour"],
                schedule_minute=schedule["schedule_minute"],
                schedule_weekday=schedule["schedule_weekday"],
                schedule_day_of_month=schedule["schedule_day_of_month"],
                timezone_name=schedule["timezone"],
            )

        return serializer.save(**extra)

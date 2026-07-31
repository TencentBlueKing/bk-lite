from rest_framework import serializers

from apps.operation_analysis.models.subscription_models import (
    DashboardReportSubscription,
)


class DashboardReportSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardReportSubscription
        fields = [
            "id",
            "dashboard",
            "creator",
            "name",
            "status",
            "recipient_email",
            "email_channel",
            "schedule_type",
            "schedule_hour",
            "schedule_minute",
            "schedule_weekday",
            "schedule_day_of_month",
            "timezone",
            "next_run_at",
            "version",
            "config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "creator",
            "next_run_at",
            "config",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            # version 可读；写时仅用于调度变更乐观锁，不直接落库
            "version": {"required": False},
        }

    def validate_status(self, value):
        if value == DashboardReportSubscription.Status.TERMINATED:
            raise serializers.ValidationError(
                "terminated 状态不可由 API 直接写入"
            )
        return value

    def validate_timezone(self, value):
        if value is None or value == "":
            return None
        from apps.operation_analysis.services.schedule_calculator import (
            validate_iana_timezone,
        )

        try:
            return validate_iana_timezone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if (
            self.instance
            and "dashboard" in attrs
            and attrs["dashboard"] != self.instance.dashboard
        ):
            raise serializers.ValidationError(
                {"dashboard": "报告订阅创建后不可更换仪表盘"}
            )
        dashboard = attrs.get(
            "dashboard",
            self.instance.dashboard if self.instance else None,
        )
        if self.instance is None and dashboard is None:
            raise serializers.ValidationError(
                {"dashboard": "创建报告订阅必须指定仪表盘"}
            )
        status = attrs.get(
            "status",
            self.instance.status
            if self.instance
            else DashboardReportSubscription.Status.ACTIVE,
        )
        email_channel = attrs.get(
            "email_channel",
            self.instance.email_channel if self.instance else None,
        )
        if (
            status == DashboardReportSubscription.Status.ACTIVE
            and dashboard is None
        ):
            raise serializers.ValidationError(
                {"dashboard": "启用状态的报告订阅必须关联仪表盘"}
            )
        if email_channel is None:
            raise serializers.ValidationError(
                {"email_channel": "报告订阅必须指定邮件通道"}
            )

        schedule_type = attrs.get(
            "schedule_type",
            self.instance.schedule_type if self.instance else None,
        )
        if schedule_type is not None:
            hour = attrs.get(
                "schedule_hour",
                self.instance.schedule_hour if self.instance else None,
            )
            minute = attrs.get(
                "schedule_minute",
                self.instance.schedule_minute if self.instance else None,
            )
            tz = attrs.get(
                "timezone",
                self.instance.timezone if self.instance else None,
            )
            if hour is None or minute is None:
                raise serializers.ValidationError(
                    {"schedule_hour": "已配置调度时必须指定时分"}
                )
            if not tz:
                raise serializers.ValidationError(
                    {"timezone": "已配置调度时必须指定 IANA 时区"}
                )
            if schedule_type == DashboardReportSubscription.ScheduleType.WEEKLY:
                weekday = attrs.get(
                    "schedule_weekday",
                    self.instance.schedule_weekday if self.instance else None,
                )
                if weekday is None:
                    raise serializers.ValidationError(
                        {"schedule_weekday": "每周调度必须指定 weekday"}
                    )
            if (
                schedule_type
                == DashboardReportSubscription.ScheduleType.MONTHLY
            ):
                day = attrs.get(
                    "schedule_day_of_month",
                    self.instance.schedule_day_of_month
                    if self.instance
                    else None,
                )
                if day is None:
                    raise serializers.ValidationError(
                        {
                            "schedule_day_of_month": (
                                "每月调度必须指定 day_of_month"
                            )
                        }
                    )
        return attrs

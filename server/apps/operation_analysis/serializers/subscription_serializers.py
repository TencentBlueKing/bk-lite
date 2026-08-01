from rest_framework import serializers

from apps.operation_analysis.models.subscription_models import (
    DashboardReportExecution,
    DashboardReportSubscription,
)


class DashboardReportExecutionSummarySerializer(serializers.ModelSerializer):
    """列表双状态摘要：scheduled / manual_test 各自最近一次。"""

    execution_id = serializers.IntegerField(source="id", read_only=True)

    class Meta:
        model = DashboardReportExecution
        fields = [
            "execution_id",
            "status",
            "trigger_type",
            "failure_stage",
            "error_code",
            "error_message",
            "created_at",
            "finished_at",
            "scheduled_time_utc",
        ]
        read_only_fields = fields


class DashboardReportSubscriptionSerializer(serializers.ModelSerializer):
    applied_filter_values = serializers.JSONField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Dashboard 当前已应用筛选（appliedFilterValues）",
    )
    latest_scheduled_execution = serializers.SerializerMethodField()
    latest_manual_test_execution = serializers.SerializerMethodField()

    class Meta:
        model = DashboardReportSubscription
        fields = [
            "id",
            "dashboard",
            "creator",
            "creator_domain",
            "team_id",
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
            "revision",
            "config",
            "applied_filter_values",
            "latest_scheduled_execution",
            "latest_manual_test_execution",
            "terminated_at",
            "terminated_by",
            "terminated_by_domain",
            "termination_reason",
            "last_lifecycle_action",
            "last_lifecycle_actor",
            "last_lifecycle_actor_domain",
            "last_lifecycle_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "creator",
            "creator_domain",
            "team_id",
            "next_run_at",
            "config",
            "latest_scheduled_execution",
            "latest_manual_test_execution",
            "terminated_at",
            "terminated_by",
            "terminated_by_domain",
            "termination_reason",
            "last_lifecycle_action",
            "last_lifecycle_actor",
            "last_lifecycle_actor_domain",
            "last_lifecycle_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            # version 可读；写时仅用于调度变更乐观锁，不直接落库
            "version": {"required": False},
            "revision": {"required": False},
        }

    def get_latest_scheduled_execution(self, obj):
        execution = self._latest_execution(
            obj,
            trigger_type=DashboardReportExecution.TriggerType.SCHEDULED,
            prefetch_attr="_latest_scheduled_executions",
        )
        if execution is None:
            return None
        return DashboardReportExecutionSummarySerializer(execution).data

    def get_latest_manual_test_execution(self, obj):
        execution = self._latest_execution(
            obj,
            trigger_type=DashboardReportExecution.TriggerType.MANUAL_TEST,
            prefetch_attr="_latest_manual_test_executions",
        )
        if execution is None:
            return None
        return DashboardReportExecutionSummarySerializer(execution).data

    @staticmethod
    def _latest_execution(obj, *, trigger_type: str, prefetch_attr: str):
        prefetched = getattr(obj, prefetch_attr, None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return (
            obj.executions.filter(trigger_type=trigger_type)
            .order_by("-id")
            .first()
        )

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

    def validate_applied_filter_values(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("已应用筛选必须是对象")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is not None and "revision" not in attrs:
            raise serializers.ValidationError(
                {"revision": "修改订阅必须携带当前 revision"}
            )
        if (
            self.instance
            and self.instance.status
            == DashboardReportSubscription.Status.TERMINATED
        ):
            raise serializers.ValidationError(
                {"status": "已终止的报告订阅不可修改或恢复"}
            )
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

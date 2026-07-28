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
            "config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "creator",
            "config",
            "created_at",
            "updated_at",
        ]

    def validate_status(self, value):
        if value == DashboardReportSubscription.Status.TERMINATED:
            raise serializers.ValidationError("Phase 1A 不允许设置 terminated")
        return value

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
        if (
            status == DashboardReportSubscription.Status.ACTIVE
            and dashboard is None
        ):
            raise serializers.ValidationError(
                {"dashboard": "启用状态的报告订阅必须关联仪表盘"}
            )
        return attrs

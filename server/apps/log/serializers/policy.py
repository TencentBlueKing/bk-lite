from rest_framework import serializers

from apps.log.models.policy import Alert, Event, EventRawData, Policy
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.utils.policy_config import validate_timing_config


class PolicySerializer(serializers.ModelSerializer):
    schedule = serializers.JSONField(required=True)
    period = serializers.JSONField(required=True)
    organizations = serializers.SerializerMethodField()
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="策略监控的日志分组ID列表",
    )

    class Meta:
        model = Policy
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "last_run_time")
        validators = []

    def get_organizations(self, obj):
        """通过外键关系获取组织列表"""
        organizations = [org.organization for org in obj.policyorganization_set.all()]
        visible_organizations = self.context.get("data_team_ids")
        if visible_organizations is None:
            return organizations
        return [organization for organization in organizations if organization in visible_organizations]

    def _get_collect_type_scope(self):
        if self.instance:
            return self.instance.collect_type_id

        initial_data = getattr(self, "initial_data", None)
        collect_type = initial_data.get("collect_type") if isinstance(initial_data, dict) else None
        if collect_type in [None, "", "null"]:
            return None

        return collect_type

    def validate_name(self, value):
        """验证策略名称唯一性"""
        collect_type = self._get_collect_type_scope()
        queryset = Policy.objects.filter(name=value)

        if collect_type is None:
            queryset = queryset.filter(collect_type__isnull=True)
        else:
            queryset = queryset.filter(collect_type=collect_type)

        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)

        if queryset.exists():
            raise serializers.ValidationError("当前范围下策略名称已存在")

        return value

    def validate_log_groups(self, value):
        """验证日志分组的有效性"""
        request = self.context.get("request") if hasattr(self, "context") else None
        if request is not None and value:
            try:
                LogAccessScopeService.resolve_scope(request, value)
            except ValueError as exc:
                raise serializers.ValidationError(str(exc))
        elif value:
            is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(value)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
        return value

    def validate_schedule(self, value):
        try:
            return validate_timing_config(value, "schedule")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_period(self, value):
        try:
            return validate_timing_config(value, "period")
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AlertSerializer(serializers.ModelSerializer):
    policy_name = serializers.SerializerMethodField()
    collect_type_name = serializers.SerializerMethodField()

    # 告警类型返回
    alert_type = serializers.SerializerMethodField()
    alert_name = serializers.SerializerMethodField()

    # 新增字段 - 改为使用SerializerMethodField
    organizations = serializers.SerializerMethodField()
    notice_users = serializers.SerializerMethodField()
    alert_condition = serializers.SerializerMethodField()
    show_fields = serializers.SerializerMethodField()
    period = serializers.SerializerMethodField()

    def get_organizations(self, obj):
        organizations = list(obj.organizations or [])
        if not organizations and obj.policy_id:
            organizations = [org.organization for org in obj.policy.policyorganization_set.all()]
        visible_organizations = self.context.get("data_team_ids")
        if visible_organizations is None:
            return organizations
        return [organization for organization in organizations if organization in visible_organizations]

    def get_collect_type_name(self, obj):
        if not obj.collect_type:
            return None
        return obj.collect_type.name

    def get_policy_name(self, obj):
        return obj.policy.name if obj.policy_id else ""

    def get_alert_type(self, obj):
        return obj.policy.alert_type if obj.policy_id else ""

    def get_notice_users(self, obj):
        return obj.policy.notice_users if obj.policy_id else []

    def get_alert_condition(self, obj):
        return obj.policy.alert_condition if obj.policy_id else {}

    def get_show_fields(self, obj):
        return obj.policy.show_fields if obj.policy_id else []

    def get_period(self, obj):
        return obj.policy.period if obj.policy_id else {}

    def get_alert_name(self, obj):
        if obj.content:
            return obj.content
        return obj.policy.alert_name if obj.policy_id else ""

    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "notice")


class EventSerializer(serializers.ModelSerializer):
    policy_name = serializers.SerializerMethodField()
    alert_id = serializers.CharField(source="alert.id", read_only=True)

    def get_policy_name(self, obj):
        return obj.policy.name if obj.policy_id else ""

    class Meta:
        model = Event
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class EventRawDataSerializer(serializers.ModelSerializer):
    event_id = serializers.CharField(source="event.id", read_only=True)
    data = serializers.JSONField(read_only=True)

    class Meta:
        model = EventRawData
        fields = "__all__"

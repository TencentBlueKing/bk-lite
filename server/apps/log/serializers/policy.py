from rest_framework import serializers

from apps.log.models.policy import Alert, Event, EventRawData, Policy
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.utils.log_group import LogGroupQueryBuilder
from apps.log.utils.policy_config import validate_timing_config
from apps.log.utils.user_display import format_user_identifiers


class AssignHandlersSerializer(serializers.Serializer):
    handlers = serializers.ListField(child=serializers.JSONField(), allow_empty=False)

    def validate_handlers(self, value):
        cleaned = []
        for item in value:
            if item in (None, "") or isinstance(item, bool):
                raise serializers.ValidationError("处理人标识无效")
            cleaned.append(item)
        if not cleaned:
            raise serializers.ValidationError("至少指定一名处理人")
        return cleaned


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

    def _policy_organization_ids(self, attrs):
        if "policy_organizations" in self.context:
            return self.context.get("policy_organizations") or []
        if self.instance is not None:
            return [rel.organization for rel in self.instance.policyorganization_set.all()]
        return []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        handlers_provided = "handlers" in attrs
        organizations_provided = "policy_organizations" in self.context
        if not handlers_provided and not organizations_provided:
            return attrs
        from apps.log.services.alert_handlers import AlertHandlerInvalid, normalize_policy_handlers

        handlers = attrs["handlers"] if handlers_provided else list(getattr(self.instance, "handlers", None) or [])
        try:
            resolved = normalize_policy_handlers(handlers, self._policy_organization_ids(attrs))
        except AlertHandlerInvalid as exc:
            raise serializers.ValidationError({"handlers": str(exc)}) from exc
        if handlers_provided:
            attrs["handlers"] = resolved
        return attrs


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
    handlers_display = serializers.SerializerMethodField()

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

    def get_handlers_display(self, obj):
        return format_user_identifiers(obj.handlers or [])

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

from rest_framework import serializers
from apps.log.models.policy import Policy, Alert, Event, EventRawData
from apps.log.utils.log_group import LogGroupQueryBuilder


class PolicySerializer(serializers.ModelSerializer):
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
        return list(obj.policyorganization_set.values_list("organization", flat=True))

    def _get_collect_type_scope(self):
        if self.instance:
            return self.instance.collect_type_id

        initial_data = getattr(self, "initial_data", None)
        collect_type = (
            initial_data.get("collect_type") if isinstance(initial_data, dict) else None
        )
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
        if value:
            is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(value)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
        return value


class AlertSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source="policy.name", read_only=True)
    collect_type_name = serializers.SerializerMethodField()

    # 告警类型返回
    alert_type = serializers.CharField(source="policy.alert_type", read_only=True)
    alert_name = serializers.CharField(source="policy.alert_name", read_only=True)

    # 新增字段 - 改为使用SerializerMethodField
    organizations = serializers.SerializerMethodField()
    notice_users = serializers.ListField(source="policy.notice_users", read_only=True)
    alert_condition = serializers.DictField(
        source="policy.alert_condition", read_only=True
    )
    show_fields = serializers.ListField(source="policy.show_fields", read_only=True)
    period = serializers.DictField(source="policy.period", read_only=True)

    def get_organizations(self, obj):
        """通过外键关系获取策略的组织列表"""
        return list(
            obj.policy.policyorganization_set.values_list("organization", flat=True)
        )

    def get_collect_type_name(self, obj):
        if not obj.collect_type:
            return None
        return obj.collect_type.name

    class Meta:
        model = Alert
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "notice")


class EventSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source="policy.name", read_only=True)
    alert_id = serializers.CharField(source="alert.id", read_only=True)

    class Meta:
        model = Event
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at")


class EventRawDataSerializer(serializers.ModelSerializer):
    event_id = serializers.CharField(source="event.id", read_only=True)

    class Meta:
        model = EventRawData
        fields = "__all__"

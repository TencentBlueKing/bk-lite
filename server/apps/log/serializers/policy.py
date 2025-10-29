from rest_framework import serializers
from apps.log.models.policy import Policy, Alert, Event, EventRawData
from apps.log.utils.log_group import LogGroupQueryBuilder


class PolicySerializer(serializers.ModelSerializer):
    organizations = serializers.SerializerMethodField()
    log_groups = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="策略监控的日志分组ID列表"
    )

    class Meta:
        model = Policy
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'last_run_time')

    def get_organizations(self, obj):
        """通过外键关系获取组织列表"""
        return list(obj.policyorganization_set.values_list('organization', flat=True))

    def validate_name(self, value):
        """验证策略名称唯一性"""
        if self.instance:
            # 更新时排除当前实例
            if Policy.objects.filter(
                name=value,
                collect_type=self.instance.collect_type
            ).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("该采集方式下策略名称已存在")
        else:
            # 创建时检查
            collect_type = self.initial_data.get('collect_type')
            if collect_type and Policy.objects.filter(name=value, collect_type=collect_type).exists():
                raise serializers.ValidationError("该采集方式下策略名称已存在")
        return value

    def validate_log_groups(self, value):
        """验证日志分组的有效性"""
        if value:
            is_valid, error_msg, _ = LogGroupQueryBuilder.validate_log_groups(value)
            if not is_valid:
                raise serializers.ValidationError(error_msg)
        return value


class AlertSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    collect_type_name = serializers.CharField(source='collect_type.name', read_only=True)

    # 告警类型返回
    alert_type = serializers.CharField(source='policy.alert_type', read_only=True)
    alert_name = serializers.CharField(source='policy.alert_name', read_only=True)

    # 新增字段 - 改为使用SerializerMethodField
    organizations = serializers.SerializerMethodField()
    notice_users = serializers.ListField(source='policy.notice_users', read_only=True)
    alert_condition = serializers.DictField(source='policy.alert_condition', read_only=True)
    show_fields = serializers.ListField(source='policy.show_fields', read_only=True)
    period = serializers.DictField(source='policy.period', read_only=True)

    def get_organizations(self, obj):
        """通过外键关系获取策略的组织列表"""
        return list(obj.policy.policyorganization_set.values_list('organization', flat=True))

    class Meta:
        model = Alert
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'notice')


class EventSerializer(serializers.ModelSerializer):
    policy_name = serializers.CharField(source='policy.name', read_only=True)
    alert_id = serializers.CharField(source='alert.id', read_only=True)

    class Meta:
        model = Event
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class EventRawDataSerializer(serializers.ModelSerializer):
    event_id = serializers.CharField(source='event.id', read_only=True)

    class Meta:
        model = EventRawData
        fields = '__all__'

from rest_framework import serializers

from apps.cmdb.constants.subscription import FilterType, TriggerType
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.utils.subscription_utils import check_subscription_manage_permission


class SubscriptionRuleSerializer(serializers.ModelSerializer):
    """订阅规则序列化器。"""

    can_manage = serializers.SerializerMethodField(help_text="当前用户是否可管理此规则")

    class Meta:
        model = SubscriptionRule
        fields = [
            "id",
            "name",
            "organization",
            "model_id",
            "filter_type",
            "instance_filter",
            "trigger_types",
            "trigger_config",
            "recipients",
            "channel_ids",
            "is_enabled",
            "last_triggered_at",
            "last_check_time",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "can_manage",
        ]
        read_only_fields = [
            "id",
            "last_triggered_at",
            "last_check_time",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "can_manage",
        ]

    def get_can_manage(self, obj) -> bool:
        """判断当前用户是否有权限管理此规则。"""
        request = self.context.get("request")
        if not request:
            return False
        return check_subscription_manage_permission(
            obj.organization, request.COOKIES.get("current_team")
        )

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("规则名称不能为空")
        return value.strip()

    def validate_instance_filter(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("instance_filter 格式不合法")

        filter_type = None
        if isinstance(self.initial_data, dict):
            filter_type = self.initial_data.get("filter_type")
        if filter_type is None and self.instance:
            filter_type = self.instance.filter_type

        if filter_type == FilterType.CONDITION.value:
            query_list = value.get("query_list", [])
            if not isinstance(query_list, list):
                raise serializers.ValidationError("query_list 必须为列表")
            if not query_list:
                raise serializers.ValidationError("至少配置一个筛选条件")
            if len(query_list) > 8:
                raise serializers.ValidationError("筛选条件最多支持 8 个")
        elif filter_type == FilterType.INSTANCES.value:
            instance_ids = value.get("instance_ids", [])
            if not isinstance(instance_ids, list):
                raise serializers.ValidationError("instance_ids 必须为列表")
            if not instance_ids:
                raise serializers.ValidationError("至少选择一个实例")
        else:
            raise serializers.ValidationError("filter_type 非法")
        return value

    def validate_trigger_types(self, value):
        valid_types = {
            TriggerType.ATTRIBUTE_CHANGE.value,
            TriggerType.RELATION_CHANGE.value,
            TriggerType.EXPIRATION.value,
        }
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少选择一种触发类型")
        if not set(value).issubset(valid_types):
            raise serializers.ValidationError("触发类型不合法")
        return value

    def validate_trigger_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("trigger_config 格式不合法")

        trigger_types = None
        if isinstance(self.initial_data, dict):
            trigger_types = self.initial_data.get("trigger_types")
        if trigger_types is None and self.instance:
            trigger_types = self.instance.trigger_types
        trigger_types = trigger_types or []
        if TriggerType.ATTRIBUTE_CHANGE.value in trigger_types:
            attr_change = value.get("attribute_change", {})
            fields = attr_change.get("fields", [])
            if not isinstance(fields, list) or not fields:
                raise serializers.ValidationError("属性变化需配置监听字段")
        if TriggerType.RELATION_CHANGE.value in trigger_types:
            related_model = value.get("relation_change", {}).get("related_model")
            if not related_model:
                raise serializers.ValidationError("关联变化需配置关联模型")
        if TriggerType.EXPIRATION.value in trigger_types:
            expiration = value.get("expiration", {})
            time_field = expiration.get("time_field")
            days_before = expiration.get("days_before")
            if not time_field:
                raise serializers.ValidationError("临近到期需配置时间字段")
            if not isinstance(days_before, int) or days_before <= 0:
                raise serializers.ValidationError("提前天数必须为正整数")
        return value

    def validate_recipients(self, value):
        users = value.get("users", [])
        groups = value.get("groups", [])
        if not isinstance(users, list) or not isinstance(groups, list):
            raise serializers.ValidationError("recipients 格式不合法")
        if not users and not groups:
            raise serializers.ValidationError("至少选择一个接收对象")
        return value

    def validate_channel_ids(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少选择一个通知渠道")
        if any(not isinstance(i, int) for i in value):
            raise serializers.ValidationError("通知渠道ID必须为整数")
        return value

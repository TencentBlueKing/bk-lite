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
            TriggerType.CONFIG_FILE.value,
        }
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("至少选择一种触发类型")
        if not set(value).issubset(valid_types):
            raise serializers.ValidationError("触发类型不合法")
        return value

    def validate_trigger_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("trigger_config 格式不合法")

        normalized_value = dict(value)

        trigger_types = None
        if isinstance(self.initial_data, dict):
            trigger_types = self.initial_data.get("trigger_types")
        if trigger_types is None and self.instance:
            trigger_types = self.instance.trigger_types
        trigger_types = trigger_types or []
        if TriggerType.ATTRIBUTE_CHANGE.value in trigger_types:
            attr_change = normalized_value.get("attribute_change", {})
            fields = attr_change.get("fields", [])
            if not isinstance(fields, list) or not fields:
                raise serializers.ValidationError("属性变化需配置监听字段")
        if TriggerType.RELATION_CHANGE.value in trigger_types:
            relation_change = normalized_value.get("relation_change", {})
            normalized_relation_change = self._normalize_relation_change_config(
                relation_change
            )
            normalized_value["relation_change"] = normalized_relation_change
        if TriggerType.EXPIRATION.value in trigger_types:
            expiration = normalized_value.get("expiration", {})
            time_field = expiration.get("time_field")
            days_before = expiration.get("days_before")
            if not time_field:
                raise serializers.ValidationError("临近到期需配置时间字段")
            if not isinstance(days_before, int) or days_before <= 0:
                raise serializers.ValidationError("提前天数必须为正整数")
        if TriggerType.CONFIG_FILE.value in trigger_types:
            config_file = normalized_value.get("config_file", {})
            if config_file is None:
                normalized_value["config_file"] = {}
            elif not isinstance(config_file, dict):
                raise serializers.ValidationError("config_file 配置格式不合法")
        return normalized_value

    @staticmethod
    def _normalize_relation_change_item(item: dict) -> dict:
        if not isinstance(item, dict):
            raise serializers.ValidationError("关联模型配置格式不合法")
        related_model = item.get("related_model")
        if not isinstance(related_model, str) or not related_model.strip():
            raise serializers.ValidationError("关联变化需配置关联模型")
        fields = item.get("fields", [])
        if not isinstance(fields, list) or not fields:
            raise serializers.ValidationError("关联变化需配置关联字段")
        return {
            "related_model": related_model.strip(),
            "fields": fields,
        }

    def _normalize_relation_change_config(self, relation_change: dict) -> dict:
        if not isinstance(relation_change, dict):
            raise serializers.ValidationError("relation_change 配置格式不合法")

        related_models_raw = relation_change.get("related_models")
        related_model_legacy = relation_change.get("related_model")
        fields_legacy = relation_change.get("fields", [])

        normalized_models: list[dict] = []
        if related_models_raw is not None:
            if not isinstance(related_models_raw, list) or not related_models_raw:
                raise serializers.ValidationError("关联变化需配置至少一个关联模型")
            normalized_models = [
                self._normalize_relation_change_item(item)
                for item in related_models_raw
            ]

        has_legacy = isinstance(related_model_legacy, str) and bool(
            related_model_legacy.strip()
        )
        if has_legacy:
            if not isinstance(fields_legacy, list) or not fields_legacy:
                raise serializers.ValidationError("关联变化需配置关联字段")
            legacy_item = {
                "related_model": related_model_legacy.strip(),
                "fields": fields_legacy,
            }
            if normalized_models:
                matched = any(
                    item["related_model"] == legacy_item["related_model"]
                    and item["fields"] == legacy_item["fields"]
                    for item in normalized_models
                )
                if not matched:
                    raise serializers.ValidationError(
                        "关联变化新旧结构配置冲突，请仅保留一种或保持一致"
                    )
            else:
                normalized_models = [legacy_item]

        if not normalized_models:
            raise serializers.ValidationError("关联变化需配置至少一个关联模型")

        seen_models: set[str] = set()
        for item in normalized_models:
            related_model = item["related_model"]
            if related_model in seen_models:
                raise serializers.ValidationError("关联模型不能重复")
            seen_models.add(related_model)

        first_item = normalized_models[0]
        return {
            "related_models": normalized_models,
            "related_model": first_item["related_model"],
            "fields": first_item["fields"],
        }

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

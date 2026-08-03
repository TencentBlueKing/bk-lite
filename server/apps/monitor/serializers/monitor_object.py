from rest_framework import serializers

from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectOrganizationRule, MonitorObjectType
from apps.monitor.utils.instance_id_keys import resolve_monitor_object_instance_id_keys


class MonitorObjectTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorObjectType
        fields = ["id", "name", "description", "order"]
        extra_kwargs = {
            "name": {"required": True},  # name 必填
            "description": {"required": False, "allow_blank": True},
            "order": {"required": False},
        }


class MonitorObjectSerializer(serializers.ModelSerializer):
    type_info = MonitorObjectTypeSerializer(source="type", read_only=True)
    cleanup_timeout_value = serializers.IntegerField(required=False, min_value=1, max_value=1440)

    class Meta:
        model = MonitorObject
        fields = "__all__"
        read_only_fields = [
            "is_builtin",
            "cleanup_policy_effective_at",
            "last_discovery_success_at",
        ]

    def _resolve_instance_id_keys(self, attrs):
        level = attrs.get("level", getattr(self.instance, "level", "base"))
        object_name = attrs.get("name", getattr(self.instance, "name", ""))
        default_keys = getattr(self.instance, "instance_id_keys", []) if self.instance is not None else []
        return resolve_monitor_object_instance_id_keys(
            attrs.get("instance_id_keys", default_keys),
            level=level,
            object_name=object_name,
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        cleanup_timeout_value = attrs.pop("cleanup_timeout_value", None)
        if cleanup_timeout_value is not None:
            legacy_value = attrs.get("cleanup_timeout_days")
            if legacy_value is not None and legacy_value != cleanup_timeout_value:
                raise serializers.ValidationError({"cleanup_timeout_value": "超时时间数值与旧字段不一致"})
            attrs["cleanup_timeout_days"] = cleanup_timeout_value
        if {"cleanup_policy", "cleanup_timeout_days", "cleanup_timeout_unit"} & attrs.keys():
            level = attrs.get("level", getattr(self.instance, "level", "base"))
            parent = attrs.get("parent", getattr(self.instance, "parent", None))
            if level != "base" or parent is not None:
                raise serializers.ValidationError({"cleanup_policy": "清理策略只能配置在一级监控对象"})
        timeout_value = attrs.get("cleanup_timeout_days", getattr(self.instance, "cleanup_timeout_days", 1))
        timeout_unit = attrs.get(
            "cleanup_timeout_unit",
            getattr(self.instance, "cleanup_timeout_unit", MonitorObject.CLEANUP_TIMEOUT_UNIT_DAY),
        )
        max_value = 1440 if timeout_unit == MonitorObject.CLEANUP_TIMEOUT_UNIT_MINUTE else 365
        if type(timeout_value) is not int or not 1 <= timeout_value <= max_value:
            unit_label = "分钟" if timeout_unit == MonitorObject.CLEANUP_TIMEOUT_UNIT_MINUTE else "天"
            raise serializers.ValidationError(
                {"cleanup_timeout_value": f"超时时间必须是 1～{max_value} {unit_label}的整数"}
            )
        attrs["instance_id_keys"] = self._resolve_instance_id_keys(attrs)
        return attrs

    def create(self, validated_data):
        validated_data["instance_id_keys"] = self._resolve_instance_id_keys(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["instance_id_keys"] = self._resolve_instance_id_keys(validated_data)
        return super().update(instance, validated_data)


class MonitorObjectOrganizationRuleSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        data_team_ids = self.context.get("data_team_ids")
        if data_team_ids is not None:
            representation["organizations"] = [
                organization for organization in representation.get("organizations", []) if organization in data_team_ids
            ]
        return representation

    class Meta:
        model = MonitorObjectOrganizationRule
        fields = "__all__"

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

    class Meta:
        model = MonitorObject
        fields = "__all__"

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

# -- coding: utf-8 --
from rest_framework import serializers

from apps.cmdb.models.custom_collect_plugin import CustomCollectPlugin
from apps.cmdb.services.custom_collect_plugin import reference_count, validate_plugin_payload
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.serializers import TeamSerializer


class CustomCollectPluginListSerializer(TeamSerializer):
    reference_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomCollectPlugin
        exclude = ("content",)

    def get_reference_count(self, obj):
        annotated = getattr(obj, "reference_count", None)
        if annotated is not None and not callable(annotated):
            return annotated
        return reference_count(obj.id)


class CustomCollectPluginSerializer(TeamSerializer):
    reference_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomCollectPlugin
        fields = "__all__"
        read_only_fields = ("content_checksum", "version", "created_by", "updated_by", "domain", "updated_by_domain", "created_at", "updated_at")

    def get_reference_count(self, obj):
        if not getattr(obj, "id", None):
            return 0
        return reference_count(obj.id)

    def validate(self, attrs):
        payload = {}
        if self.instance is not None:
            payload = {
                "name": self.instance.name,
                "plugin_id": self.instance.plugin_id,
                "model_id": self.instance.model_id,
                "os_type": self.instance.os_type,
                "shell": self.instance.shell,
                "content": self.instance.content,
                "desc": self.instance.desc,
                "team": self.instance.team,
            }
        payload.update(attrs)
        try:
            normalized = validate_plugin_payload(payload, instance=self.instance)
        except BaseAppException as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return normalized

    def create(self, validated_data):
        return CustomCollectPlugin.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance

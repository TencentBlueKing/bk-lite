# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.models.models import Level
from apps.alerts.utils.i18n import serializer_message


class LevelModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Level
        fields = "__all__"

    def validate_level_id(self, value):
        if value is None:
            raise serializers.ValidationError(serializer_message(self, "error.level_value_empty"))
        if value < 0:
            raise serializers.ValidationError(serializer_message(self, "error.level_value_non_negative"))
        return value

    def validate_icon(self, value):
        if not value:
            return value

        if value.startswith("data:image/"):
            return value

        if len(value) > 100:
            raise serializers.ValidationError(serializer_message(self, "error.default_icon_too_long"))

        return value

    def validate(self, attrs):
        instance = self.instance

        if instance is not None:
            if "level_id" in attrs and attrs["level_id"] != instance.level_id:
                raise serializers.ValidationError({"level_id": serializer_message(self, "error.level_id_immutable")})
            if "level_type" in attrs and attrs["level_type"] != instance.level_type:
                raise serializers.ValidationError({"level_type": serializer_message(self, "error.level_type_immutable")})

        level_type = attrs.get("level_type", getattr(instance, "level_type", None))
        level_id = attrs.get("level_id", getattr(instance, "level_id", None))

        if level_type is not None and level_id is not None:
            queryset = Level.objects.filter(level_type=level_type, level_id=level_id)
            if instance is not None:
                queryset = queryset.exclude(pk=instance.pk)
            if queryset.exists():
                raise serializers.ValidationError({"level_id": serializer_message(self, "error.level_value_exists")})

        return attrs
